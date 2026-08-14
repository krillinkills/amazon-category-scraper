from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

ROBOT_MARKERS = (
    'enter the characters you see below',
    'validateCaptcha',
    '/errors/validateCaptcha',
    'api-services-support@amazon.com',
    'sorry, we just need to make sure you',
)

DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
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
}


class AmazonBlockedError(RuntimeError):
    """Amazon returned a robot check or an empty blocked page."""


class AmazonRetryableError(RuntimeError):
    """Transient Amazon/proxy failure that should be retried with a new IP."""


def accept_language_for(marketplace: str) -> str:
    return ACCEPT_LANGUAGE.get((marketplace or '').upper(), DEFAULT_HEADERS['Accept-Language'])


def request_headers(marketplace: str | None = None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if marketplace:
        headers['Accept-Language'] = accept_language_for(marketplace)
    return headers


def product_url(domain: str, asin: str) -> str:
    return f'https://{domain}/dp/{asin}'


def _is_blocked(html: str) -> bool:
    lowered = html.casefold()
    return any(marker.casefold() in lowered for marker in ROBOT_MARKERS)


def create_session(
    max_clients: int,
    proxy_url: str | None = None,
    impersonate: str = 'chrome',
) -> AsyncSession:
    kwargs: dict[str, Any] = {
        'impersonate': impersonate,
        'max_clients': max_clients,
        'timeout': 35,
    }
    if proxy_url:
        kwargs['proxies'] = {'http': proxy_url, 'https': proxy_url}
    return AsyncSession(**kwargs)


async def fetch_html(
    url: str,
    proxy_url: str | None = None,
    timeout: int = 35,
    session: AsyncSession | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    owns_session = session is None
    if session is None:
        session = create_session(max_clients=1, proxy_url=proxy_url)
    try:
        try:
            response = await session.get(
                url,
                headers=headers or DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )
        except Exception as error:
            raise AmazonRetryableError(f'Request failed for {url}: {error}') from error

        if response.status_code in {429, 500, 502, 503, 504}:
            raise AmazonRetryableError(f'HTTP {response.status_code} on {url}')
        if response.status_code >= 400:
            raise AmazonRetryableError(f'HTTP {response.status_code} on {url}')
        html = response.text or ''
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
    soup = BeautifulSoup(html, 'lxml')
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
        '#productDetails_detailBullets_sections1 tr'
    )
    for row in rows:
        key = _text(row.select_one('th, td.a-span3, span.a-text-bold, span.a-color-secondary'))
        value = _text(row.select_one('td.po-break-word, td.a-span9, td:last-child'))
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
        '#feature-bullets li'
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


def parse_product_detail(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, 'lxml')
    brand = None
    description = None

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
            'tr.po-brand span.po-break-word',
            '#productOverview_feature_div tr.po-brand td.po-break-word',
        ]))

    overview = _product_overview(soup)
    if not brand and overview:
        for key, value in overview.items():
            if key.casefold() in {'brand', 'manufacturer', 'marca', 'marke'}:
                brand = _clean_brand(value)
                break

    if not description:
        description = _text(soup.select_one('#productDescription, #productDescription p'))

    about = _about_this_item(soup)
    return {
        'brand': brand,
        'aboutThisItem': about or [],
        'description': description,
        'productOverview': overview,
    }


async def polite_pause(minimum: float = 2.0, maximum: float = 4.5) -> None:
    await asyncio.sleep(random.uniform(minimum, maximum))
