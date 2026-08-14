from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from apify import Actor

from .category_tree import CategoryLookupError, listing_url, resolve_category_input
from .scraper import (
    EMPTY_PRODUCT_DETAILS,
    PDP_CUT_MARKERS,
    PDP_KEEP_MARKERS,
    AmazonBlockedError,
    AmazonRetryableError,
    has_core_details,
    parse_listing_cards,
    parse_product_detail,
    polite_pause,
    product_fetch_url,
    product_url,
    request_headers,
)
from .sticky import LISTING_REQUESTS_PER_IP, MAX_REQUESTS_PER_IP, StickyProxySession


DEFAULT_CONCURRENCY = 100
MAX_CONCURRENCY = 150


def _parse_optional_limit(value: Any, *, field: str) -> int | None:
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{field} must be an integer. Use 0 for no limit.') from error
    if parsed <= 0:
        return None
    return parsed


def _reached_limit(count: int, limit: int | None) -> bool:
    return limit is not None and count >= limit


def _listing_record(
    card: dict[str, Any],
    *,
    resolved: Any,
    run_meta: dict[str, Any],
    position: int,
    page: int,
    listing_page_url: str,
) -> dict[str, Any]:
    asin = card['asin']
    return {
        **card,
        **EMPTY_PRODUCT_DETAILS,
        **run_meta,
        'url': product_url(resolved.domain, asin),
        'currency': resolved.currency,
        'position': position,
        'page': page,
        'listingUrl': listing_page_url,
        'hasDetails': False,
        'recordType': 'listing',
    }


async def _collect_listing(
    *,
    listing: StickyProxySession,
    resolved: Any,
    run_meta: dict[str, Any],
    listing_headers: dict[str, str],
    max_pages: int | None,
    max_items: int | None,
    on_item: Any | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch every category page first. Returns unique product cards and page count."""
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 0

    while not _reached_limit(len(collected), max_items):
        if max_pages is not None and page >= max_pages:
            break
        page += 1

        url = listing_url(resolved, page)
        Actor.log.info(f'Listing page {page}: {url}')

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
                Actor.log.info(f'No listing cards on page {page} after retries, stopping listing.')
                if page == 1:
                    raise RuntimeError(f'No product cards found on {url}')
                break

        page_added = 0
        for position, card in enumerate(cards, start=1):
            if _reached_limit(len(collected), max_items):
                break
            asin = card['asin']
            if asin in seen:
                continue
            seen.add(asin)
            record = _listing_record(
                card,
                resolved=resolved,
                run_meta=run_meta,
                position=position,
                page=page,
                listing_page_url=url,
            )
            collected.append(record)
            if on_item is not None:
                await on_item(record)
            page_added += 1

        Actor.log.info(
            f'Listing page {page}: {page_added} products (total {len(collected)}).'
        )
        if page_added == 0:
            Actor.log.info(f'Listing page {page} had no new ASINs, stopping listing.')
            break
        more_pages = max_pages is None or page < max_pages
        if more_pages and not _reached_limit(len(collected), max_items):
            await polite_pause(0.2, 0.6)

    return collected, page


async def _enrich_item(
    item: dict[str, Any],
    *,
    sticky: StickyProxySession,
    domain: str,
    headers: dict[str, str],
    attempts: int = 2,
    abort_after_product_block: bool = True,
) -> dict[str, Any] | None:
    url = product_fetch_url(domain, item['asin'])
    last_error: Exception | None = None
    abort_kwargs: dict[str, Any] = {}
    if abort_after_product_block:
        abort_kwargs = {
            'abort_after': PDP_CUT_MARKERS,
            'abort_requires': PDP_KEEP_MARKERS,
        }
    for attempt in range(1, attempts + 1):
        try:
            html = await sticky.fetch(url, headers, **abort_kwargs)
        except (AmazonBlockedError, AmazonRetryableError, Exception) as error:
            last_error = error
            Actor.log.warning(
                f'{sticky.name} attempt {attempt}/{attempts} failed for {url}: {error}'
            )
            await sticky.rotate(f'{type(error).__name__} on attempt {attempt}')
            if attempt < attempts:
                if isinstance(error, AmazonBlockedError):
                    await polite_pause(0.6, 1.4)
                else:
                    await polite_pause(0.15, 0.5)
            continue

        if not getattr(_enrich_item, '_logged_pdp_size', False):
            _enrich_item._logged_pdp_size = True  # type: ignore[attr-defined]
            Actor.log.info(f'First PDP {item["asin"]}: {len(html)} chars downloaded')

        details = await asyncio.to_thread(parse_product_detail, html)
        if has_core_details(details):
            return {**item, **details}

        last_error = AmazonRetryableError('empty product detail page')
        Actor.log.warning(
            f'{sticky.name} attempt {attempt}/{attempts} got no brand/overview for {item["asin"]}'
        )
        await sticky.rotate('empty product detail page')
        if attempt < attempts:
            await polite_pause(0.15, 0.5)

    Actor.log.warning(f'Detail page incomplete for {item["asin"]}: {last_error}')
    return None


async def _enrich_all(
    items: list[dict[str, Any]],
    *,
    proxy_configuration: Any,
    domain: str,
    headers: dict[str, str],
    concurrency: int,
) -> tuple[int, int]:
    """Open product pages. Store only rows with brand, bullets, or overview."""
    if not items:
        return 0, 0

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    start_gate = asyncio.Semaphore(25)
    retry_lock = asyncio.Lock()
    retries: list[dict[str, Any]] = []
    pushed = 0
    missed = 0
    pass_name = 'pass1'

    async def worker(index: int) -> None:
        nonlocal pushed, missed
        sticky = StickyProxySession(
            proxy_configuration,
            name=f'pdp{index}',
            max_requests=MAX_REQUESTS_PER_IP,
        )
        try:
            while True:
                payload = await queue.get()
                try:
                    if payload is None:
                        return
                    if sticky.http is None:
                        async with start_gate:
                            await sticky.start()
                    attempts = 2 if pass_name == 'pass1' else 3
                    record = await _enrich_item(
                        payload,
                        sticky=sticky,
                        domain=domain,
                        headers=headers,
                        attempts=attempts,
                        abort_after_product_block=pass_name == 'pass1',
                    )
                    if record and has_core_details(record):
                        await Actor.push_data({
                            **record,
                            'hasDetails': True,
                            'recordType': 'detail',
                        })
                        pushed += 1
                        if pushed == 1:
                            Actor.log.info(f'First detailed product written: {record.get("asin")}')
                        if pushed % 25 == 0:
                            Actor.log.info(
                                f'Stored {pushed} detailed products ({missed} still missing details).'
                            )
                    elif pass_name == 'pass1':
                        async with retry_lock:
                            retries.append(payload)
                    else:
                        missed += 1
                except Exception as error:
                    Actor.log.exception(
                        f'pdp{index} failed on {payload.get("asin") if payload else "?"}: {error}'
                    )
                    if payload and pass_name == 'pass1':
                        async with retry_lock:
                            retries.append(payload)
                    elif payload:
                        missed += 1
                finally:
                    queue.task_done()
        finally:
            await sticky.close()

    workers = [asyncio.create_task(worker(index)) for index in range(concurrency)]
    Actor.log.info(
        f'{concurrency} detail workers starting on {len(items)} products '
        f'(sticky IP per worker, rotate every {MAX_REQUESTS_PER_IP} requests or on block). '
        'Rows are stored only when brand, About this item, or overview parsed.'
    )
    try:
        for item in items:
            await queue.put(item)
        await queue.join()

        retry_batch = list(retries)
        retries.clear()
        if retry_batch:
            pass_name = 'pass2'
            Actor.log.info(
                f'Retrying {len(retry_batch)} products that had no brand/overview.'
            )
            for item in retry_batch:
                await queue.put(item)
            await queue.join()

        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers, return_exceptions=True)
    except Exception:
        for worker_task in workers:
            worker_task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    return pushed, missed


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        marketplace = actor_input.get('marketplace')
        category = actor_input.get('category')
        department = actor_input.get('department')
        subcategory = actor_input.get('subcategory')
        pages_input = actor_input.get('pages', actor_input.get('maxPages'))
        max_pages = _parse_optional_limit(pages_input, field='pages / maxPages')
        max_items = _parse_optional_limit(actor_input.get('maxItems'), field='maxItems')
        enrich_details = actor_input.get('enrichDetails', True)
        if isinstance(enrich_details, str):
            enrich_details = enrich_details.strip().lower() not in {'0', 'false', 'no'}
        concurrency = max(1, min(int(actor_input.get('maxConcurrency') or DEFAULT_CONCURRENCY), MAX_CONCURRENCY))

        if not marketplace:
            raise ValueError('marketplace is required.')
        if not category and not (department and subcategory):
            raise ValueError('category is required, e.g. "Mobiles, Computers -> All Mobile Phones".')

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

        scraped_at = datetime.now(timezone.utc).replace(microsecond=0)
        scraped_at_iso = scraped_at.strftime('%Y-%m-%dT%H:%M:%SZ')
        scraped_date = scraped_at.strftime('%Y-%m-%d')
        proxy_input = actor_input.get('proxyConfiguration') or {}
        run_meta = {
            'scrapedAt': scraped_at_iso,
            'scrapedDate': scraped_date,
            'runId': Actor.configuration.actor_run_id,
            'marketplace': resolved.marketplace,
            'marketName': resolved.market_name,
            'domain': resolved.domain,
            'browseNodeId': resolved.browse_node_id,
            'department': resolved.department,
            'subcategory': resolved.subcategory,
            'categoryPath': resolved.category_path,
            'proxyCountry': proxy_input.get('apifyProxyCountry'),
        }

        pages_label = 'unlimited pages' if max_pages is None else f'max {max_pages} pages'
        items_label = 'unlimited items' if max_items is None else f'{max_items} items'
        Actor.log.info(
            f'Scraping {resolved.marketplace} {resolved.category_path} '
            f'on {resolved.domain} node={resolved.browse_node_id} '
            f'({pages_label}, {items_label}, '
            f'details={"on" if enrich_details else "off"}, concurrency={concurrency}, '
            f'sticky IPs rotate every {MAX_REQUESTS_PER_IP} product pages). '
            'Phase 1 collects every listing card; phase 2 opens product pages.'
        )

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get('proxyConfiguration'),
        )
        listing_headers = request_headers()
        detail_headers = request_headers(resolved.marketplace)

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
        listing_pages = 0
        collected: list[dict[str, Any]] = []

        async def _store_listing_card(record: dict[str, Any]) -> None:
            nonlocal pushed
            await Actor.push_data(record)
            pushed += 1

        try:
            collected, listing_pages = await _collect_listing(
                listing=listing,
                resolved=resolved,
                run_meta=run_meta,
                listing_headers=listing_headers,
                max_pages=max_pages,
                max_items=max_items,
                on_item=None if enrich_details else _store_listing_card,
            )
            queued = len(collected)
        finally:
            await listing.close()

        if not enrich_details:
            Actor.log.info(f'Done. Stored {pushed} listing cards from {listing_pages} pages.')
        else:
            Actor.log.info(
                f'Listing done: {queued} products from {listing_pages} pages. '
                f'Opening product pages with {concurrency} workers.'
            )
            pushed, detail_fail = await _enrich_all(
                collected,
                proxy_configuration=proxy_configuration,
                domain=resolved.domain,
                headers=detail_headers,
                concurrency=concurrency,
            )
            detail_ok = pushed
            Actor.log.info(
                f'Done. Stored {pushed} products with brand/overview '
                f'({detail_fail} ASINs omitted after retries).'
            )

        await Actor.set_value('SCRAPE_META', {
            **run_meta,
            'maxPages': max_pages,
            'maxItems': max_items,
            'enrichDetails': enrich_details,
            'maxConcurrency': concurrency,
            'listingPages': listing_pages,
            'itemsQueued': queued,
            'itemsStored': pushed,
            'detailOk': detail_ok,
            'detailFail': detail_fail,
            'finishedAt': datetime.now(timezone.utc).replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ'),
        })
