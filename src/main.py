from __future__ import annotations

from apify import Actor

from .category_tree import CategoryLookupError, listing_url, resolve_category
from .scraper import AmazonBlockedError, fetch_html, parse_listing_cards, polite_pause


async def _proxy_url(proxy_configuration):
    if not proxy_configuration:
        return None
    return await proxy_configuration.new_url()


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        marketplace = actor_input.get('marketplace')
        department = actor_input.get('department')
        subcategory = actor_input.get('subcategory')
        max_pages = int(actor_input.get('maxPages') or 3)
        max_items = int(actor_input.get('maxItems') or 60)

        if not marketplace or not department or not subcategory:
            raise ValueError('marketplace, department, and subcategory are required.')

        try:
            resolved = resolve_category(str(marketplace), str(department), str(subcategory))
        except CategoryLookupError as error:
            Actor.log.error(str(error))
            raise

        Actor.log.info(
            f'Scraping {resolved.marketplace} {resolved.category_path} '
            f'on {resolved.domain} (max {max_pages} pages, {max_items} items)'
        )

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=actor_input.get('proxyConfiguration'),
        )
        proxy_url = await _proxy_url(proxy_configuration)

        pushed = 0
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            if pushed >= max_items:
                break

            url = listing_url(resolved, page)
            Actor.log.info(f'Fetching page {page}: {url}')

            try:
                try:
                    html = fetch_html(url, proxy_url)
                except AmazonBlockedError:
                    proxy_url = await _proxy_url(proxy_configuration)
                    Actor.log.warning('Blocked on first try, retrying with a fresh proxy.')
                    html = fetch_html(url, proxy_url)
            except AmazonBlockedError as error:
                Actor.log.error(str(error))
                if page == 1:
                    raise
                break
            except Exception as error:
                Actor.log.error(f'Failed to fetch {url}: {error}')
                if page == 1:
                    raise
                break

            cards = parse_listing_cards(html, resolved.domain)
            if not cards:
                Actor.log.info(f'No listing cards on page {page}, stopping.')
                if page == 1:
                    raise RuntimeError(f'No product cards found on {url}')
                break

            page_added = 0
            for position, card in enumerate(cards, start=1):
                if pushed >= max_items:
                    break
                asin = card['asin']
                if asin in seen:
                    continue
                seen.add(asin)
                await Actor.push_data({
                    **card,
                    'currency': resolved.currency,
                    'position': position,
                    'page': page,
                    'marketplace': resolved.marketplace,
                    'department': resolved.department,
                    'subcategory': resolved.subcategory,
                    'categoryPath': resolved.category_path,
                })
                pushed += 1
                page_added += 1

            Actor.log.info(f'Page {page}: stored {page_added} items (total {pushed}).')
            if page < max_pages and pushed < max_items:
                polite_pause()

        Actor.log.info(f'Done. Stored {pushed} products.')
