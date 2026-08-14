from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi import CurlOpt
from curl_cffi.const import CurlECode
from curl_cffi.curl import CURL_WRITEFUNC_ERROR
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException

ROBOT_MARKERS = (
    'enter the characters you see below',
    'validateCaptcha',
    '/errors/validateCaptcha',
    'api-services-support@amazon.com',
    'sorry, we just need to make sure you',
    'automated access to amazon',
    'click the button below to continue',
    'to continue shopping',
    'sorry, something went wrong on our end',
)

DEFAULT_HEADERS = {
    'Accept-Language': 'en-US,en;q=0.9',
}

ACCEPT_LANGUAGE = {
    'US': 'en-US,en;q=0.9',
    'CA': 'en-CA,en;q=0.9',
    'GB': 'en-GB,en;q=0.9',
    'IE': 'en-IE,en;q=0.9',
    'IN': 'en-IN,en;q=0.9',
    'AU': 'en-AU,en;q=0.9',
    'SG': 'en-SG,en;q=0.9',
    'ZA': 'en-ZA,en;q=0.9',
    'AE': 'en-AE,en;q=0.9',
    'SA': 'en-SA,en;q=0.9',
    'EG': 'en-EG,en;q=0.9',
    'DE': 'de-DE,de;q=0.9,en;q=0.8',
    'FR': 'fr-FR,fr;q=0.9,en;q=0.8',
    'IT': 'it-IT,it;q=0.9,en;q=0.8',
    'ES': 'es-ES,es;q=0.9,en;q=0.8',
    'NL': 'nl-NL,nl;q=0.9,en;q=0.8',
    'BE': 'nl-BE,fr-BE,en;q=0.8',
    'SE': 'sv-SE,sv;q=0.9,en;q=0.8',
    'PL': 'pl-PL,pl;q=0.9,en;q=0.8',
    'TR': 'tr-TR,tr;q=0.9,en;q=0.8',
    'JP': 'ja-JP,ja;q=0.9,en;q=0.8',
    'MX': 'es-MX,es;q=0.9,en;q=0.8',
    'BR': 'pt-BR,pt;q=0.9,en;q=0.8',
}

BULLET_SKIP = (
    'make sure this fits',
    'see more product details',
    'to see product details',
    'click to see',
    'javascript',
    'your browser',
)

EMPTY_PRODUCT_DETAILS = {
    'brand': None,
    'aboutThisItem': None,
    'description': None,
    'productOverview': None,
    'productCategory': None,
    'productCategories': None,
    'productCategoryPath': None,
    'productBrowseNodeId': None,
}

REQUEST_TIMEOUT = 18
LOW_SPEED_LIMIT_BYTES = 2_000
LOW_SPEED_TIME_SECONDS = 8

# Drop everything after the product block. Reviews / A+ / recs are huge and unused.
PDP_CUT_MARKERS = (
    'id="aplus"',
    "id='aplus'",
    'id="aplus_feature_div"',
    'id="dpx-aplus-product-description_feature_div"',
    'id="reviewsMedley"',
    'id="customerReviews"',
    'id="similarities_feature_div"',
    'id="purchase-similarities_feature_div"',
)
LISTING_CUT_MARKERS = (
    'id="navFooter"',
)

# Only cut after these widgets. Do not use JSON-LD as the floor: it sits in
# <head>, and an early #rhf / #aplus placeholder would drop the product body.
PDP_KEEP_MARKERS = (
    'id="feature-bullets"',
    'id="featurebullets_feature_div"',
    'id="productFactsDesktopExpander"',
    'id="productFactsDesktop_feature_div"',
    'id="productOverview_feature_div"',
    'id="productDescription"',
    'id="detailBullets_feature_div"',
    'id="detailBulletsWrapper_feature_div"',
    'id="bylineInfo"',
    'id="wayfinding-breadcrumbs_feature_div"',
)


def has_product_details(details: dict[str, Any]) -> bool:
    about = details.get('aboutThisItem')
    return bool(
        details.get('brand')
        or details.get('description')
        or details.get('productCategoryPath')
        or details.get('productOverview')
        or (isinstance(about, list) and about)
    )


def has_core_details(details: dict[str, Any]) -> bool:
    """Brand, bullets, or overview — not breadcrumb-only JSON-LD."""
    about = details.get('aboutThisItem')
    return bool(
        details.get('brand')
        or details.get('productOverview')
        or (isinstance(about, list) and about)
    )


class AmazonBlockedError(RuntimeError):
    """Amazon returned a robot check or an empty blocked page."""


class AmazonRetryableError(RuntimeError):
    """Transient Amazon/proxy failure that should be retried with a new IP."""


def accept_language_for(marketplace: str) -> str:
    return ACCEPT_LANGUAGE.get((marketplace or '').upper(), DEFAULT_HEADERS['Accept-Language'])


def request_headers(marketplace: str | None = None, *, referer: str | None = None) -> dict[str, str]:
    """Only override Accept-Language / Referer so curl_cffi can keep Chrome's other headers."""
    headers = {'Accept-Language': accept_language_for(marketplace or '')}
    if referer:
        headers['Referer'] = referer
    return headers


def listing_fetch_debug(html: str) -> str:
    title = ''
    match = re.search(r'<title[^>]*>([^<]+)', html or '', re.I)
    if match:
        title = re.sub(r'\s+', ' ', match.group(1)).strip()[:90]
    has_search = 'data-component-type="s-search-result"' in (html or '')
    has_asin = 'data-asin="' in (html or '')
    return f'{len(html or "")} chars, title={title!r}, search-result={has_search}, data-asin={has_asin}'


def product_url(domain: str, asin: str) -> str:
    return f'https://{domain}/dp/{asin}'


def product_fetch_url(domain: str, asin: str) -> str:
    """Canonical /dp URL plus variation flags so Amazon skips the parent picker."""
    return f'https://{domain}/dp/{asin}?th=1&psc=1'


def _is_blocked(html: str) -> bool:
    lowered = html.casefold()
    return any(marker.casefold() in lowered for marker in ROBOT_MARKERS)


def _strip_elements(html: str, tag: str, *, keep_if: str | None = None) -> str:
    """Remove <tag>...</tag> blocks without a DOTALL regex over megabyte pages."""
    open_tag = f'<{tag}'
    close_tag = f'</{tag}>'
    close_len = len(close_tag)
    parts: list[str] = []
    pos = 0
    while True:
        start = html.find(open_tag, pos)
        if start == -1:
            parts.append(html[pos:])
            break
        gt = html.find('>', start)
        if gt == -1:
            parts.append(html[pos:])
            break
        opening = html[start:gt + 1]
        end = html.find(close_tag, gt)
        if keep_if and keep_if in opening.casefold():
            if end == -1:
                parts.append(html[pos:])
                break
            parts.append(html[pos:end + close_len])
            pos = end + close_len
            continue
        parts.append(html[pos:start])
        pos = end + close_len if end != -1 else gt + 1
    return ''.join(parts)


def _cut_after_markers(
    html: str,
    markers: tuple[str, ...],
    *,
    after: tuple[str, ...] = (),
) -> str:
    floor = 0
    found_after = False
    for token in after:
        idx = html.find(token)
        if idx != -1:
            found_after = True
            floor = max(floor, idx)
    if after and not found_after:
        return html
    cut_at: int | None = None
    for marker in markers:
        idx = html.find(marker)
        if idx != -1 and idx > floor and (cut_at is None or idx < cut_at):
            cut_at = idx
    if cut_at is None:
        return html
    return html[:cut_at]


def thin_product_html(html: str) -> str:
    """Keep JSON-LD + product markup; drop JS bundles, CSS, SVG, reviews, A+."""
    html = _strip_elements(html, 'script', keep_if='ld+json')
    html = _strip_elements(html, 'style')
    html = _strip_elements(html, 'svg')
    html = _strip_elements(html, 'noscript')
    return _cut_after_markers(html, PDP_CUT_MARKERS, after=PDP_KEEP_MARKERS)


def thin_listing_html(html: str) -> str:
    html = _strip_elements(html, 'script', keep_if='ld+json')
    html = _strip_elements(html, 'style')
    html = _strip_elements(html, 'svg')
    html = _strip_elements(html, 'noscript')
    return _cut_after_markers(html, LISTING_CUT_MARKERS, after=('data-component-type="s-search-result"',))


class _EarlyAbortBuffer:
    """Collect HTML and tell curl to hang up once the product block is in."""

    def __init__(self, cut: tuple[str, ...], require: tuple[str, ...]) -> None:
        self.cut = cut
        self.require = require
        self.chunks: list[bytes] = []
        self.aborted = False
        self._found_keep = False
        self._tail = ''
        self._overlap = max(len(token) for token in cut + require)

    def __call__(self, chunk: bytes) -> int:
        self.chunks.append(chunk)
        piece = chunk.decode('latin-1')
        haystack = self._tail + piece
        if not self._found_keep:
            self._found_keep = any(token in haystack for token in self.require)
        if self._found_keep and any(token in haystack for token in self.cut):
            self.aborted = True
            return CURL_WRITEFUNC_ERROR
        self._tail = haystack[-self._overlap:]
        return len(chunk)

    def text(self) -> str:
        return b''.join(self.chunks).decode('utf-8', errors='replace')


def create_session(
    max_clients: int,
    proxy_url: str | None = None,
    impersonate: str = 'chrome',
) -> AsyncSession:
    kwargs: dict[str, Any] = {
        'impersonate': impersonate,
        'max_clients': max_clients,
        'timeout': REQUEST_TIMEOUT,
        'curl_options': {
            CurlOpt.LOW_SPEED_LIMIT: LOW_SPEED_LIMIT_BYTES,
            CurlOpt.LOW_SPEED_TIME: LOW_SPEED_TIME_SECONDS,
        },
    }
    if proxy_url:
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    return AsyncSession(**kwargs)


async def fetch_html(
    url: str,
    proxy_url: str | None = None,
    timeout: int = REQUEST_TIMEOUT,
    session: AsyncSession | None = None,
    headers: dict[str, str] | None = None,
    *,
    abort_after: tuple[str, ...] | None = None,
    abort_requires: tuple[str, ...] | None = None,
) -> str:
    owns_session = session is None
    if session is None:
        session = create_session(max_clients=1, proxy_url=proxy_url)
    abort_buf = (
        _EarlyAbortBuffer(abort_after, abort_requires)
        if abort_after and abort_requires
        else None
    )
    try:
        status = 0
        html = ''
        try:
            get_kwargs: dict[str, Any] = {
                'timeout': timeout,
                'allow_redirects': True,
                'content_callback': abort_buf,
            }
            if headers:
                get_kwargs['headers'] = headers
            response = await session.get(url, **get_kwargs)
            status = response.status_code
            html = abort_buf.text() if abort_buf is not None else (response.text or '')
        except RequestException as error:
            aborted = (
                abort_buf is not None
                and abort_buf.aborted
                and error.code == CurlECode.WRITE_ERROR
            )
            if not aborted:
                raise AmazonRetryableError(f'Request failed for {url}: {error}') from error
            status = error.response.status_code if error.response is not None else 200
            html = abort_buf.text()
        except Exception as error:
            raise AmazonRetryableError(f'Request failed for {url}: {error}') from error

        if status in {429, 500, 502, 503, 504}:
            raise AmazonRetryableError(f'HTTP {status} on {url}')
        if status >= 400:
            raise AmazonRetryableError(f'HTTP {status} on {url}')
    finally:
        if owns_session:
            await session.close()

    if _is_blocked(html):
        raise AmazonBlockedError(f'Amazon robot check on {url}')
    return html


def _text(node) -> str | None:
    if not node:
        return None
    value = node.get_text(' ', strip=True)
    return value or None


def _first_text(card, selectors: list[str]) -> str | None:
    for selector in selectors:
        value = _text(card.select_one(selector))
        if value:
            return value
    return None


def _absolute_url(href: str | None, domain: str) -> str | None:
    if not href:
        return None
    if href.startswith('http://') or href.startswith('https://'):
        return href.split('?')[0]
    if href.startswith('/'):
        return f'https://{domain}{href.split("?")[0]}'
    return None


def _parse_price(raw: str | None) -> str | None:
    if not raw:
        return None
    return re.sub(r'\s+', ' ', raw).strip() or None


def _parse_rating(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r'(\d+(?:\.\d+)?)', raw.replace(',', '.'))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r'[^\d]', '', raw)
    if not digits:
        return None
    return int(digits)


def parse_listing_cards(html: str, domain: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(thin_listing_html(html), 'lxml')
    cards = soup.select('div[data-component-type="s-search-result"][data-asin]')
    if not cards:
        cards = [
            node
            for node in soup.select('[data-asin]')
            if node.get('data-asin')
        ]

    items: list[dict[str, Any]] = []
    for card in cards:
        asin = (card.get('data-asin') or '').strip()
        if not asin:
            continue

        title = _first_text(card, [
            'h2 a span',
            'h2 span',
            'h2',
            '.s-title-instructions-style span',
            'a.a-link-normal span.a-text-normal',
            'span.a-text-normal',
        ])
        link = card.select_one('h2 a[href], a.a-link-normal[href]')
        href = link.get('href') if link else None
        if not title and href:
            title = _title_from_href(href)
        image = card.select_one('img.s-image, img[src]')
        image_url = image.get('src') if image else None

        price = _parse_price(_first_text(card, [
            '.a-price .a-offscreen',
            '.a-price-whole',
        ]))
        original_price = _parse_price(_first_text(card, [
            '.a-text-price .a-offscreen',
            'span.a-price[data-a-strike="true"] .a-offscreen',
        ]))

        rating = _parse_rating(_first_text(card, [
            'span.a-icon-alt',
            '[aria-label*="out of"]',
        ]))
        reviews = _parse_int(_first_text(card, [
            'span[aria-label$="ratings"]',
            'span[aria-label$="rating"]',
            'a[href*="#customerReviews"] span',
            '.s-underline-text',
        ]))

        is_sponsored = bool(card.select_one(
            '.puis-sponsored-label-text, .s-sponsored-label-text, .s-sponsored-label-info-text'
        ))
        is_prime = bool(card.select_one('[aria-label="Amazon Prime"], .s-prime, i.a-icon-prime'))

        badge = _first_text(card, [
            '.a-badge-text',
            '.puis-status-badge-text',
            'span.a-badge-label-inner',
        ])
        bought = _first_text(card, [
            '.a-size-base.a-color-secondary',
        ])
        if bought and 'bought' not in bought.casefold():
            bought = None

        items.append({
            'asin': asin,
            'title': title,
            'url': _absolute_url(href, domain) or product_url(domain, asin),
            'image': image_url,
            'price': price,
            'originalPrice': original_price,
            'rating': rating,
            'reviewsCount': reviews,
            'isSponsored': is_sponsored,
            'isPrime': is_prime,
            'badge': badge,
            'boughtInPastMonth': bought,
        })
    return items


def _title_from_href(href: str) -> str | None:
    path = href.split('?', 1)[0].strip('/')
    parts = [part for part in path.split('/') if part]
    if 'dp' in parts:
        index = parts.index('dp')
        if index > 0:
            slug = parts[index - 1].replace('-', ' ').strip()
            return slug or None
    return None


def _walk_json_ld(data: Any):
    if isinstance(data, list):
        for item in data:
            yield from _walk_json_ld(item)
        return
    if not isinstance(data, dict):
        return
    graph = data.get('@graph')
    if graph:
        yield from _walk_json_ld(graph)
        return
    yield data


def _ld_brand(node: dict) -> str | None:
    brand = node.get('brand')
    if isinstance(brand, str):
        return _clean_brand(brand)
    if isinstance(brand, dict):
        return _clean_brand(brand.get('name') or brand.get('brand'))
    manufacturer = node.get('manufacturer')
    if isinstance(manufacturer, str):
        return _clean_brand(manufacturer)
    if isinstance(manufacturer, dict):
        return _clean_brand(manufacturer.get('name'))
    return None


def _clean_brand(raw: str | None) -> str | None:
    if not raw:
        return None
    text = re.sub(r'\s+', ' ', raw).strip()
    text = re.sub(r'^visit the\s+', '', text, flags=re.I)
    text = re.sub(r'\s+store$', '', text, flags=re.I)
    text = re.sub(r'^brand:\s*', '', text, flags=re.I)
    if not text or text.casefold() in {'visit amazon', 'amazon'}:
        return None
    return text


def _keep_bullet(text: str) -> bool:
    lowered = text.casefold()
    if len(text) < 3:
        return False
    return not any(skip in lowered for skip in BULLET_SKIP)


def _product_overview(soup: BeautifulSoup) -> dict[str, str] | None:
    overview: dict[str, str] = {}
    rows = soup.select(
        '#productOverview_feature_div tr, '
        'table.a-normal.a-spacing-micro tr, '
        '#productDetails_techSpec_section_1 tr, '
        '#productDetails_detailBullets_sections1 tr, '
        '#productFactsDesktopExpander tr, '
        '#productFactsDesktop_feature_div tr, '
        '#tech-specs-desktop tr'
    )
    for row in rows:
        key = _text(row.select_one('th, td.a-span3, span.a-text-bold, span.a-color-secondary'))
        value = _text(row.select_one(
            'td.po-break-word, span.po-break-word, td.a-span9, td:last-child'
        ))
        if not key or not value or key == value:
            continue
        key = key.rstrip(':').strip()
        if key and key not in overview:
            overview[key] = value
    return overview or None


def _about_this_item(soup: BeautifulSoup) -> list[str]:
    bullets: list[str] = []
    seen: set[str] = set()
    nodes = soup.select(
        '#feature-bullets ul li span.a-list-item, '
        '#featurebullets_feature_div li span.a-list-item, '
        '#feature-bullets li, '
        '#productFactsDesktopExpander li, '
        '#productFactsDesktop_feature_div li, '
        '#productFactsDesktopExpander .a-list-item, '
        '#featurebullets_feature_div li, '
        '#detailBullets_feature_div li span.a-list-item, '
        '#detailBulletsWrapper_feature_div li span.a-list-item, '
        'div[data-feature-name="featurebullets"] li span.a-list-item'
    )
    for node in nodes:
        text = _text(node)
        if not text or not _keep_bullet(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        bullets.append(text)
    return bullets


def _browse_node_id(href: str | None) -> str | None:
    if not href:
        return None
    match = re.search(r'[?&]node=(\d+)', href)
    return match.group(1) if match else None


def _skip_crumb_name(name: str) -> bool:
    lowered = name.casefold()
    return lowered in {'›', '>', '/', 'amazon', 'amazon.in', 'amazon.com'} or lowered.startswith('amazon.')


def _crumbs_from_wayfinding(soup: BeautifulSoup) -> list[dict[str, str | None]]:
    crumbs: list[dict[str, str | None]] = []
    for link in soup.select(
        '#wayfinding-breadcrumbs_feature_div a, '
        '#wayfinding-breadcrumbs_container a, '
        'div.a-breadcrumb a'
    ):
        name = _text(link)
        if not name or _skip_crumb_name(name):
            continue
        crumbs.append({
            'name': name,
            'browseNodeId': _browse_node_id(link.get('href')),
        })
    return crumbs


def _crumbs_from_json_ld(node: dict) -> list[dict[str, str | None]]:
    types = node.get('@type')
    type_names = types if isinstance(types, list) else [types]
    if 'BreadcrumbList' not in {name for name in type_names if name}:
        return []
    elements = node.get('itemListElement') or []
    if not isinstance(elements, list):
        return []
    ordered: list[tuple[int, dict[str, str | None]]] = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        url = item.get('item')
        if isinstance(url, dict):
            name = name or url.get('name')
            url = url.get('@id') or url.get('url') or url.get('item')
        if not isinstance(name, str):
            continue
        name = re.sub(r'\s+', ' ', name).strip()
        if not name or _skip_crumb_name(name):
            continue
        position = item.get('position')
        try:
            rank = int(position)
        except (TypeError, ValueError):
            rank = len(ordered)
        ordered.append((rank, {
            'name': name,
            'browseNodeId': _browse_node_id(url if isinstance(url, str) else None),
        }))
    ordered.sort(key=lambda pair: pair[0])
    return [crumb for _, crumb in ordered]


def _product_category_fields(crumbs: list[dict[str, str | None]]) -> dict[str, Any]:
    names = [crumb['name'] for crumb in crumbs if crumb.get('name')]
    leaf = crumbs[-1] if crumbs else None
    return {
        'productCategory': leaf['name'] if leaf else None,
        'productCategories': names or None,
        'productCategoryPath': ' > '.join(names) if names else None,
        'productBrowseNodeId': leaf.get('browseNodeId') if leaf else None,
    }


def _parse_product_detail_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, 'lxml')
    brand = None
    description = None
    crumbs = _crumbs_from_wayfinding(soup)

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ''
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk_json_ld(payload):
            if not crumbs:
                crumbs = _crumbs_from_json_ld(node)
            types = node.get('@type')
            type_names = types if isinstance(types, list) else [types]
            if not any(name in {'Product', 'IndividualProduct'} for name in type_names if name):
                continue
            brand = brand or _ld_brand(node)
            if not description:
                value = node.get('description')
                if isinstance(value, str) and value.strip():
                    description = re.sub(r'\s+', ' ', value).strip()

    if not brand:
        brand = _clean_brand(_first_text(soup, [
            '#bylineInfo',
            'a#bylineInfo',
            '#bylineInfo_feature_div #bylineInfo',
            'tr.po-brand span.po-break-word',
            '#productOverview_feature_div tr.po-brand span.po-break-word',
            '#productOverview_feature_div tr.po-brand td.po-break-word',
            '#productFactsDesktopExpander tr.po-brand td.po-break-word',
            'a#brand',
        ]))

    overview = _product_overview(soup)
    if not brand and overview:
        for key, value in overview.items():
            if key.casefold() in {'brand', 'manufacturer', 'marca', 'marke'}:
                brand = _clean_brand(value)
                break

    if not description:
        description = _text(soup.select_one(
            '#productDescription, #productDescription p, #productDescription_feature_div'
        ))

    about = _about_this_item(soup)
    return {
        'brand': brand,
        'aboutThisItem': about or [],
        'description': description,
        'productOverview': overview,
        **_product_category_fields(crumbs),
    }


def parse_product_detail(html: str) -> dict[str, Any]:
    details = _parse_product_detail_html(thin_product_html(html))
    if has_core_details(details):
        return details
    return _parse_product_detail_html(html)


async def polite_pause(minimum: float = 0.2, maximum: float = 0.6) -> None:
    await asyncio.sleep(random.uniform(minimum, maximum))
