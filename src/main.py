from __future__ import annotations

import asyncio
from typing import Any

from apify import Actor
from curl_cffi.requests import AsyncSession

from .category_tree import CategoryLookupError, listing_url, resolve_category_input
from .scraper import (
    EMPTY_PRODUCT_DETAILS,
    AmazonBlockedError,
    AmazonRetryableError,
    create_session,
    fetch_html,
    parse_listing_cards,
    parse_product_detail,
    polite_pause,
    product_url,
    request_headers,
)


async def _proxy_url(proxy_configuration):
    if not proxy_configuration:
        return None
    return await proxy_configuration.new_url()


async def _fetch_with_retries(
    url: str,
    *,
    session: AsyncSession,
    proxy_configuration,
    proxy_url: str | None,
    headers: dict[str, str],
    attempts: int,
    rotate_every_try: bool,
) -> tuple[str | None, str | None, Exception | None]:
    last_error: Exception | None = None
    current_proxy = proxy_url
    for attempt in range(1, attempts + 1):
        if rotate_every_try or (attempt > 1):
            current_proxy = await _proxy_url(proxy_configuration)
        try:
            html = await fetch_html(url, current_proxy, session=session, headers=headers)
            return html, current_proxy, None
        except (AmazonBlockedError, AmazonRetryableError, Exception) as error:
            last_error = error
            Actor.log.warning(f'Attempt {attempt}/{attempts} failed for {url}: {error}')
            if attempt < attempts:
                await polite_pause(1.0, 2.5)
    return None, current_proxy, last_error


async def _enrich_item(
    item: dict[str, Any],
    *,
    session: AsyncSession,
    proxy_configuration,
    domain: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    url = product_url(domain, item['asin'])
    html, _, error = await _fetch_with_retries(
        url,
        session=session,
        proxy_configuration=proxy_configuration,
        proxy_url=None,
        headers=headers,
        attempts=3,
        rotate_every_try=True,
    )
    if html is None:
        Actor.log.warning(f'Detail page failed for {item["asin"]}: {error}')
        return {**item, **EMPTY_PRODUCT_DETAILS}

    details = await asyncio.to_thread(parse_product_detail, html)
    return {**item, **details}


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        marketplace = actor_input.get('marketplace')
        category = actor_input.get('category')
        department = actor_input.get('department')
        subcategory = actor_input.get('subcategory')
        pages_input = actor_input.get('pages', actor_input.get('maxPages'))
        max_items = int(actor_input.get('maxItems') or 1000)
        enrich_details = actor_input.get('enrichDetails', True)
        if isinstance(enrich_details, str):
            enrich_details = enrich_details.strip().lower() not in {'0', 'false', 'no'}
        concurrency = max(1, min(int(actor_input.get('maxConcurrency') or 50), 50))

        if not marketplace:
            raise ValueError('marketplace is required.')
        if not category and not (department and subcategory):
            raise ValueError('category is required, e.g. "Mobiles, Computers -> All Mobile Phones".')
        if pages_input is None:
            raise ValueError('pages / maxPages is required. Tell the actor how many listing pages to fetch.')
        max_pages = int(pages_input)
        if max_pages < 1:
            raise ValueError('pages must be at least 1.')
        max_pages = min(max_pages, 20)

        try:
            resolved = resolve_category_input(
                str(marketplace),
                category=str(category) if category else None,
                department=str(department) if department else None,
                subcategory=str(subcategory) if subcategory else None,
            )
        except CategoryLookupError as error:
            Actor.log.error(str(error))
            raise

        Actor.log.info(
            f'Scraping {resolved.marketplace} {resolved.category_path} '
            f'on {resolved.domain} (max {max_pages} pages, {max_items} items, '
            f'details={"on" if enrich_details else "off"}, concurrency={concurrency})'
        )

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get('proxyConfiguration'),
        )
        listing_headers = request_headers()
        detail_headers = request_headers(resolved.marketplace)
        worker_count = min(concurrency, max_items) if enrich_details else 0
        session = create_session(max_clients=max(worker_count, 1) + 2)
        listing_proxy = await _proxy_url(proxy_configuration)

        queued = 0
        pushed = 0
        detail_ok = 0
        detail_fail = 0
        seen: set[str] = set()
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=max(worker_count, 1) * 2)

        async def worker() -> None:
            nonlocal pushed, detail_ok, detail_fail
            while True:
                payload = await queue.get()
                try:
                    if payload is None:
                        return
                    record = await _enrich_item(
                        payload,
                        session=session,
                        proxy_configuration=proxy_configuration,
                        domain=resolved.domain,
                        headers=detail_headers,
                    )
                    if record.get('brand') or record.get('aboutThisItem') or record.get('description'):
                        detail_ok += 1
                    else:
                        detail_fail += 1
                    await Actor.push_data(record)
                    pushed += 1
                    if pushed % 25 == 0:
                        Actor.log.info(
                            f'Enriched {pushed} products ({detail_ok} with details, {detail_fail} listing-only).'
                        )
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]

        try:
            for page in range(1, max_pages + 1):
                if queued >= max_items:
                    break

                url = listing_url(resolved, page)
                Actor.log.info(f'Fetching page {page}: {url}')

                html, listing_proxy, last_error = await _fetch_with_retries(
                    url,
                    session=session,
                    proxy_configuration=proxy_configuration,
                    proxy_url=listing_proxy,
                    headers=listing_headers,
                    attempts=4,
                    rotate_every_try=False,
                )
                if html is None:
                    message = f'Failed to fetch {url}: {last_error}'
                    Actor.log.error(message)
                    if page == 1:
                        raise RuntimeError(message) from last_error
                    break

                cards = await asyncio.to_thread(parse_listing_cards, html, resolved.domain)
                if not cards:
                    Actor.log.warning(f'No listing cards on page {page}; treating as a soft block and retrying.')
                    html, listing_proxy, _ = await _fetch_with_retries(
                        url,
                        session=session,
                        proxy_configuration=proxy_configuration,
                        proxy_url=None,
                        headers=listing_headers,
                        attempts=3,
                        rotate_every_try=True,
                    )
                    cards = await asyncio.to_thread(parse_listing_cards, html, resolved.domain) if html else []
                    if not cards:
                        Actor.log.info(f'No listing cards on page {page} after retries, stopping.')
                        if page == 1:
                            raise RuntimeError(f'No product cards found on {url}')
                        break

                page_added = 0
                for position, card in enumerate(cards, start=1):
                    if queued >= max_items:
                        break
                    asin = card['asin']
                    if asin in seen:
                        continue
                    seen.add(asin)
                    record = {
                        **card,
                        'url': product_url(resolved.domain, asin),
                        'currency': resolved.currency,
                        'position': position,
                        'page': page,
                        'marketplace': resolved.marketplace,
                        'department': resolved.department,
                        'subcategory': resolved.subcategory,
                        'categoryPath': resolved.category_path,
                    }
                    if enrich_details:
                        await queue.put(record)
                    else:
                        await Actor.push_data(record)
                        pushed += 1
                    queued += 1
                    page_added += 1

                Actor.log.info(
                    f'Page {page}: {"queued" if enrich_details else "stored"} {page_added} items (total {queued}).'
                )
                if page < max_pages and queued < max_items:
                    await polite_pause()
        finally:
            for _ in workers:
                await queue.put(None)
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            await session.close()

        Actor.log.info(
            f'Done. Stored {pushed} products'
            + (f' ({detail_ok} with details, {detail_fail} listing-only).' if enrich_details else '.')
        )
