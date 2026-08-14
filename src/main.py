from __future__ import annotations

import asyncio
import random
from typing import Any

from apify import Actor

from .category_tree import CategoryLookupError, listing_url, resolve_category_input
from .scraper import (
    EMPTY_PRODUCT_DETAILS,
    parse_listing_cards,
    parse_product_detail,
    polite_pause,
    product_url,
    request_headers,
)
from .sticky import LISTING_REQUESTS_PER_IP, MAX_REQUESTS_PER_IP, StickyProxySession


async def _enrich_item(
    item: dict[str, Any],
    *,
    sticky: StickyProxySession,
    domain: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    url = product_url(domain, item['asin'])
    html, error = await sticky.fetch_with_retries(url, headers, attempts=3)
    if html is None:
        Actor.log.warning(f'Detail page failed for {item["asin"]}: {error}')
        return {**item, **EMPTY_PRODUCT_DETAILS}

    details = await asyncio.to_thread(parse_product_detail, html)
    await asyncio.sleep(random.uniform(0.05, 0.18))
    return {**item, **details}


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        marketplace = actor_input.get('marketplace')
        category = actor_input.get('category')
        department = actor_input.get('department')
        subcategory = actor_input.get('subcategory')
        pages_input = actor_input.get('pages', actor_input.get('maxPages'))
        max_items = int(actor_input.get('maxItems') or 5000)
        enrich_details = actor_input.get('enrichDetails', True)
        if isinstance(enrich_details, str):
            enrich_details = enrich_details.strip().lower() not in {'0', 'false', 'no'}
        concurrency = max(1, min(int(actor_input.get('maxConcurrency') or 50), 100))

        if not marketplace:
            raise ValueError('marketplace is required.')
        if not category and not (department and subcategory):
            raise ValueError('category is required, e.g. "Mobiles, Computers -> All Mobile Phones".')
        if pages_input is None:
            raise ValueError('pages / maxPages is required. Tell the actor how many listing pages to fetch.')
        max_pages = int(pages_input)
        if max_pages < 1:
            raise ValueError('pages must be at least 1.')
        max_pages = min(max_pages, 100)

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
            f'details={"on" if enrich_details else "off"}, concurrency={concurrency}, '
            f'sticky IPs rotate every {MAX_REQUESTS_PER_IP} product pages)'
        )

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get('proxyConfiguration'),
        )
        listing_headers = request_headers()
        detail_headers = request_headers(resolved.marketplace)
        worker_count = min(concurrency, max_items) if enrich_details else 0

        listing = StickyProxySession(
            proxy_configuration,
            name='listing',
            max_requests=LISTING_REQUESTS_PER_IP,
        )
        await listing.start()

        queued = 0
        pushed = 0
        detail_ok = 0
        detail_fail = 0
        seen: set[str] = set()
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=max(worker_count, 1) * 2)

        async def worker(index: int) -> None:
            nonlocal pushed, detail_ok, detail_fail
            sticky = StickyProxySession(
                proxy_configuration,
                name=f'pdp-{index}',
                max_requests=MAX_REQUESTS_PER_IP,
            )
            await sticky.start()
            try:
                while True:
                    payload = await queue.get()
                    try:
                        if payload is None:
                            return
                        record = await _enrich_item(
                            payload,
                            sticky=sticky,
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
            finally:
                await sticky.close()

        workers = [asyncio.create_task(worker(index)) for index in range(worker_count)]
        if worker_count:
            Actor.log.info(
                f'Started {worker_count} sticky PDP workers '
                f'(rotate every {MAX_REQUESTS_PER_IP} requests or on block).'
            )

        try:
            for page in range(1, max_pages + 1):
                if queued >= max_items:
                    break

                url = listing_url(resolved, page)
                Actor.log.info(f'Fetching page {page}: {url}')

                html, last_error = await listing.fetch_with_retries(
                    url, listing_headers, attempts=4,
                )
                if html is None:
                    message = f'Failed to fetch {url}: {last_error}'
                    Actor.log.error(message)
                    if page == 1:
                        raise RuntimeError(message) from last_error
                    break

                cards = await asyncio.to_thread(parse_listing_cards, html, resolved.domain)
                if not cards:
                    Actor.log.warning(f'No listing cards on page {page}; rotating listing IP and retrying.')
                    await listing.rotate('empty listing page')
                    html, _ = await listing.fetch_with_retries(url, listing_headers, attempts=3)
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
            await listing.close()

        Actor.log.info(
            f'Done. Stored {pushed} products'
            + (f' ({detail_ok} with details, {detail_fail} listing-only).' if enrich_details else '.')
        )
