from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from apify import Actor

from .category_tree import (
    CategoryLookupError,
    listing_url_candidates,
    resolve_category_input,
)
from .scraper import (
    EMPTY_PRODUCT_DETAILS,
    LISTING_CUT_MARKERS,
    LISTING_MAX_BYTES,
    PDP_CUT_MARKERS,
    PDP_EXTRA_AFTER_KEEP,
    PDP_KEEP_MARKERS,
    PDP_MAX_BYTES,
    AmazonBlockedError,
    AmazonRetryableError,
    has_core_details,
    listing_fetch_debug,
    parse_listing_cards,
    parse_product_detail,
    polite_pause,
    product_fetch_url,
    product_url,
    request_headers,
)
from .sticky import (
    LISTING_FETCH_ATTEMPTS,
    LISTING_PAGE1_ATTEMPTS,
    LISTING_REQUESTS_PER_IP,
    MAX_REQUESTS_PER_IP,
    StickyProxySession,
    retry_pause_seconds,
)


DEFAULT_CONCURRENCY = 20
MAX_CONCURRENCY = 80
DETAIL_QUEUE_MAX = 200


def proxy_country_for_marketplace(marketplace: str) -> str:
    code = (marketplace or '').strip().upper()
    if code == 'UK':
        return 'GB'
    return code


def proxy_input_with_marketplace_country(proxy_input: Any, marketplace: str) -> dict[str, Any]:
    """Pin residential IPs to the Amazon store country when the user left country empty."""
    filled = dict(proxy_input or {})
    if filled.get('useApifyProxy') is False:
        return filled
    if filled.get('apifyProxyCountry'):
        return filled
    filled['useApifyProxy'] = True
    filled.setdefault('apifyProxyGroups', ['RESIDENTIAL'])
    filled['apifyProxyCountry'] = proxy_country_for_marketplace(marketplace)
    return filled


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
    stop: asyncio.Event | None = None,
) -> tuple[int, int]:
    """Walk listing pages. Yields cards via on_item. Returns (yielded, pages)."""
    yielded = 0
    seen: set[str] = set()
    page = 0

    def _halt() -> bool:
        if stop is not None and stop.is_set():
            return True
        if stop is None and _reached_limit(yielded, max_items):
            return True
        return False

    while not _halt():
        if max_pages is not None and page >= max_pages:
            break
        page += 1

        candidates = listing_url_candidates(resolved, page)
        attempts = LISTING_PAGE1_ATTEMPTS if page == 1 else LISTING_FETCH_ATTEMPTS
        html = None
        last_error: Exception | None = None
        cards: list[dict[str, Any]] = []
        url = candidates[0]
        Actor.log.info(f'Listing page {page}: {url}')
        for attempt in range(1, attempts + 1):
            url = candidates[(attempt - 1) % len(candidates)]
            if attempt == 1 or url != candidates[(attempt - 2) % len(candidates)]:
                if attempt > 1:
                    Actor.log.info(f'Listing page {page} trying {url}')
            html, last_error = await listing.fetch_with_retries(
                url,
                listing_headers,
                attempts=1,
                abort_after=LISTING_CUT_MARKERS,
                abort_requires=('data-component-type="s-search-result"',),
                max_bytes=LISTING_MAX_BYTES,
            )
            if html:
                cards = await asyncio.to_thread(parse_listing_cards, html, resolved.domain)
                if cards:
                    break
                last_error = AmazonRetryableError(
                    f'no product cards ({listing_fetch_debug(html)})'
                )
                Actor.log.warning(
                    f'listing attempt {attempt}/{attempts} failed for {url}: {last_error}'
                )
                await listing.rotate('empty listing page')
            if attempt < attempts:
                await asyncio.sleep(
                    retry_pause_seconds(
                        last_error or AmazonRetryableError('listing fetch failed'),
                        attempt,
                    )
                )

        if not cards:
            message = f'Failed to fetch {url}: {last_error}'
            Actor.log.error(message)
            if page == 1:
                raise RuntimeError(message) from last_error
            break

        page_added = 0
        for position, card in enumerate(cards, start=1):
            if _halt():
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
            yielded += 1
            if on_item is not None:
                await on_item(record)
            page_added += 1

        Actor.log.info(
            f'Listing page {page}: {page_added} products (total {yielded}).'
        )
        if page_added == 0:
            Actor.log.info(f'Listing page {page} had no new ASINs, stopping listing.')
            break
        more_pages = max_pages is None or page < max_pages
        if more_pages and not _halt():
            await polite_pause(0.2, 0.6)

    return yielded, page


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
    abort_kwargs: dict[str, Any] = {
        'max_bytes': PDP_MAX_BYTES,
    }
    if abort_after_product_block:
        abort_kwargs.update({
            'abort_after': PDP_CUT_MARKERS,
            'abort_requires': PDP_KEEP_MARKERS,
            'extra_after_keep': PDP_EXTRA_AFTER_KEEP,
        })
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
                await asyncio.sleep(retry_pause_seconds(error, attempt))
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


async def _run_detail_pipeline(
    *,
    listing: StickyProxySession,
    resolved: Any,
    run_meta: dict[str, Any],
    listing_headers: dict[str, str],
    detail_headers: dict[str, str],
    proxy_configuration: Any,
    max_pages: int | None,
    max_items: int | None,
    concurrency: int,
) -> tuple[int, int, int, int]:
    """Listing produces ASINs; detail workers consume them at the same time.

    Returns (stored, missed, queued, listing_pages).
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=DETAIL_QUEUE_MAX)
    stop = asyncio.Event()
    start_gate = asyncio.Semaphore(25)
    retry_lock = asyncio.Lock()
    push_lock = asyncio.Lock()
    retries: list[dict[str, Any]] = []
    pushed = 0
    missed = 0
    queued = 0
    pdp_bytes = 0
    pass_name = 'pass1'

    async def enqueue(record: dict[str, Any]) -> None:
        nonlocal queued
        if stop.is_set():
            return
        await queue.put(record)
        queued += 1

    async def worker(index: int) -> None:
        nonlocal pushed, missed, pdp_bytes
        sticky = StickyProxySession(
            proxy_configuration,
            name=f'pdp{index}',
            max_requests=MAX_REQUESTS_PER_IP,
            origin=f'https://{resolved.domain}',
        )
        try:
            while True:
                payload = await queue.get()
                try:
                    if payload is None:
                        return
                    if _reached_limit(pushed, max_items):
                        stop.set()
                        continue
                    if sticky.http is None:
                        async with start_gate:
                            await sticky.start()
                    attempts = 1 if pass_name == 'pass1' else 2
                    record = await _enrich_item(
                        payload,
                        sticky=sticky,
                        domain=resolved.domain,
                        headers=detail_headers,
                        attempts=attempts,
                        abort_after_product_block=pass_name == 'pass1',
                    )
                    if record and has_core_details(record):
                        async with push_lock:
                            if _reached_limit(pushed, max_items):
                                stop.set()
                                continue
                            await Actor.push_data({
                                **record,
                                'hasDetails': True,
                                'recordType': 'detail',
                            })
                            pushed += 1
                            hit_limit = _reached_limit(pushed, max_items)
                        if pushed == 1:
                            Actor.log.info(f'First detailed product written: {record.get("asin")}')
                        if pushed % 25 == 0:
                            Actor.log.info(
                                f'Stored {pushed} detailed products ({missed} still missing details).'
                            )
                        if hit_limit:
                            stop.set()
                            Actor.log.info(
                                f'Reached maxItems={max_items}; stopping listing and extra detail fetches.'
                            )
                    elif pass_name == 'pass1' and not _reached_limit(pushed, max_items):
                        async with retry_lock:
                            retries.append(payload)
                    elif pass_name != 'pass1':
                        missed += 1
                except Exception as error:
                    Actor.log.exception(
                        f'pdp{index} failed on {payload.get("asin") if payload else "?"}: {error}'
                    )
                    if payload and pass_name == 'pass1' and not _reached_limit(pushed, max_items):
                        async with retry_lock:
                            retries.append(payload)
                    elif payload and pass_name != 'pass1':
                        missed += 1
                finally:
                    queue.task_done()
        finally:
            pdp_bytes += sticky.bytes_downloaded
            await sticky.close()

    workers = [asyncio.create_task(worker(index)) for index in range(concurrency)]
    Actor.log.info(
        f'{concurrency} detail workers ready (queue cap {DETAIL_QUEUE_MAX}, '
        f'sticky IP per worker, rotate every {MAX_REQUESTS_PER_IP} requests or on block). '
        'Listing continues while product pages open. '
        'Rows are stored only when brand, About this item, or overview parsed.'
    )
    listing_pages = 0
    listing_bytes = 0
    try:
        try:
            _, listing_pages = await _collect_listing(
                listing=listing,
                resolved=resolved,
                run_meta=run_meta,
                listing_headers=listing_headers,
                max_pages=max_pages,
                max_items=None,
                on_item=enqueue,
                stop=stop,
            )
        finally:
            listing_bytes = listing.bytes_downloaded
            await listing.close()
        Actor.log.info(
            f'Listing finished: {queued} unique ASINs from {listing_pages} pages. '
            'Waiting for in-flight product pages.'
        )
        await queue.join()

        retry_batch = list(retries)
        retries.clear()
        need_more = not _reached_limit(pushed, max_items)
        if retry_batch and need_more:
            pass_name = 'pass2'
            Actor.log.info(
                f'Retrying {len(retry_batch)} products that had no brand/overview.'
            )
            for item in retry_batch:
                if _reached_limit(pushed, max_items):
                    break
                await queue.put(item)
            await queue.join()

        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers, return_exceptions=True)
    except Exception:
        stop.set()
        for worker_task in workers:
            worker_task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    html_mb = (listing_bytes + pdp_bytes) / (1024 * 1024)
    Actor.log.info(
        f'Downloaded ~{html_mb:.1f} MB HTML '
        f'(listing {listing_bytes / (1024 * 1024):.1f} MB, '
        f'product pages {pdp_bytes / (1024 * 1024):.1f} MB). '
        'Residential proxy bills this transfer at about $7.50/GB.'
    )
    return pushed, missed, queued, listing_pages


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
            raise ValueError(
                'Pick department and subcategory, or a category path '
                'like "Mobiles, Computers -> All Mobile Phones".'
            )

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
        proxy_input = proxy_input_with_marketplace_country(
            actor_input.get('proxyConfiguration'),
            resolved.marketplace,
        )
        if not (actor_input.get('proxyConfiguration') or {}).get('apifyProxyCountry'):
            Actor.log.info(
                f'Proxy country was empty; using {proxy_input.get("apifyProxyCountry")} '
                f'to match {resolved.domain}.'
            )
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
            'Listing and product-detail fetches run at the same time.'
        )

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=proxy_input,
        )
        origin = f'https://{resolved.domain}'
        listing_headers = request_headers(resolved.marketplace, referer=f'{origin}/')
        detail_headers = request_headers(resolved.marketplace, referer=f'{origin}/')

        listing = StickyProxySession(
            proxy_configuration,
            name='listing',
            max_requests=LISTING_REQUESTS_PER_IP,
            origin=origin,
        )
        await listing.start()

        queued = 0
        pushed = 0
        detail_ok = 0
        detail_fail = 0
        listing_pages = 0

        async def _store_listing_card(record: dict[str, Any]) -> None:
            nonlocal pushed
            await Actor.push_data(record)
            pushed += 1

        if not enrich_details:
            try:
                queued, listing_pages = await _collect_listing(
                    listing=listing,
                    resolved=resolved,
                    run_meta=run_meta,
                    listing_headers=listing_headers,
                    max_pages=max_pages,
                    max_items=max_items,
                    on_item=_store_listing_card,
                )
            finally:
                await listing.close()
            Actor.log.info(f'Done. Stored {pushed} listing cards from {listing_pages} pages.')
        else:
            pushed, detail_fail, queued, listing_pages = await _run_detail_pipeline(
                listing=listing,
                resolved=resolved,
                run_meta=run_meta,
                listing_headers=listing_headers,
                detail_headers=detail_headers,
                proxy_configuration=proxy_configuration,
                max_pages=max_pages,
                max_items=max_items,
                concurrency=concurrency,
            )
            detail_ok = pushed
            Actor.log.info(
                f'Done. Stored {pushed} products with brand/overview '
                f'({detail_fail} ASINs omitted after retries, {queued} queued from listing).'
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
