from __future__ import annotations

import random
import re
import time
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi import requests

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


class AmazonBlockedError(RuntimeError):
    """Amazon returned a robot check or an empty blocked page."""


def _is_blocked(html: str) -> bool:
    lowered = html.casefold()
    return any(marker.casefold() in lowered for marker in ROBOT_MARKERS)


def fetch_html(url: str, proxy_url: str | None = None, timeout: int = 30) -> str:
    proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
    response = requests.get(
        url,
        impersonate='chrome',
        headers=DEFAULT_HEADERS,
        proxies=proxies,
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    html = response.text or ''
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
        ])
        link = card.select_one('h2 a[href], a.a-link-normal[href]')
        href = link.get('href') if link else None
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
            'url': _absolute_url(href, domain) or f'https://{domain}/dp/{asin}',
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


def polite_pause() -> None:
    time.sleep(random.uniform(1.0, 2.2))
