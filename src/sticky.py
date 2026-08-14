"""Sticky residential IPs with rotation, same pattern as the Reddit scraper.

Each worker keeps one Apify proxy session id (one upstream IP) and reuses the
curl connection. The IP is retired on a block/timeout, or proactively after a
fixed number of requests so a single address does not accumulate heat.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from apify import Actor
from curl_cffi.requests import AsyncSession

from .scraper import (
    AmazonBlockedError,
    AmazonRetryableError,
    create_session,
    fetch_html,
)

IMPERSONATE_POOL = (
    'chrome131',
    'chrome136',
    'chrome124',
    'chrome120',
)
DEFAULT_IMPERSONATE = 'chrome131'
MAX_REQUESTS_PER_IP = 25
LISTING_REQUESTS_PER_IP = 15
LISTING_FETCH_ATTEMPTS = 8
LISTING_PAGE1_ATTEMPTS = 12
_SLOW_RETRY_MARKERS = ('HTTP 429', 'HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504')


def retry_pause_seconds(error: Exception, attempt: int) -> float:
    """Wait longer after Amazon 503/429/blocks so a new IP can cool down."""
    text = str(error)
    slow = isinstance(error, AmazonBlockedError) or any(marker in text for marker in _SLOW_RETRY_MARKERS)
    if slow:
        return min(12.0, 1.25 * (2 ** (attempt - 1))) + random.uniform(0.25, 0.75)
    return random.uniform(0.15, 0.5)


class StickyProxySession:
    def __init__(
        self,
        proxy_configuration: Any | None,
        *,
        name: str,
        max_requests: int = MAX_REQUESTS_PER_IP,
        origin: str | None = None,
    ) -> None:
        self.proxy_configuration = proxy_configuration
        self.name = name
        self.max_requests = max_requests
        self.origin = origin.rstrip('/') if origin else None
        self.session_id: str | None = None
        self.http: AsyncSession | None = None
        self.requests_on_ip = 0
        self.rotations = 0
        self._warmed = False

    async def start(self) -> None:
        await self.rotate('start')

    async def rotate(self, reason: str) -> None:
        if self.http is not None:
            await self.http.close()
            self.http = None
        self.session_id = f'{self.name}_{random.randint(0, 1_000_000_000)}'
        proxy_url = None
        if self.proxy_configuration is not None:
            proxy_url = await self.proxy_configuration.new_url(self.session_id)
        profile = random.choice(IMPERSONATE_POOL)

        def _open(impersonate: str) -> AsyncSession:
            return create_session(max_clients=2, proxy_url=proxy_url, impersonate=impersonate)

        try:
            self.http = await asyncio.to_thread(_open, profile)
        except Exception:
            self.http = await asyncio.to_thread(_open, DEFAULT_IMPERSONATE)
        self.requests_on_ip = 0
        self.rotations += 1
        self._warmed = False
        if reason != 'start':
            Actor.log.info(f'Rotated sticky IP {self.name} -> {self.session_id} ({reason})')

    async def _warmup(self, headers: dict[str, str]) -> None:
        if self._warmed or not self.origin or self.http is None:
            return
        try:
            await fetch_html(f'{self.origin}/', session=self.http, headers=headers)
        except (AmazonBlockedError, AmazonRetryableError) as error:
            # US CloudFront often 503s the first hit while setting session cookies.
            Actor.log.info(f'{self.name} homepage warmup got {error}; keeping IP for listing')
        except Exception as error:
            Actor.log.warning(f'{self.name} homepage warmup failed: {error}')
        self.requests_on_ip += 1
        self._warmed = True

    async def fetch(
        self,
        url: str,
        headers: dict[str, str],
        **fetch_kwargs: Any,
    ) -> str:
        if self.http is None:
            await self.start()
        if self.requests_on_ip >= self.max_requests:
            await self.rotate(f'proactive after {self.requests_on_ip} requests')
        assert self.http is not None
        if not self._warmed and self.origin:
            await self._warmup(headers)
        try:
            html = await fetch_html(url, session=self.http, headers=headers, **fetch_kwargs)
        except AmazonRetryableError as error:
            if not any(code in str(error) for code in ('HTTP 503', 'HTTP 429', 'HTTP 502')):
                raise
            Actor.log.info(f'{self.name} {error}; retrying once on the same IP')
            html = await fetch_html(url, session=self.http, headers=headers, **fetch_kwargs)
        self.requests_on_ip += 1
        return html

    async def fetch_with_retries(
        self,
        url: str,
        headers: dict[str, str],
        *,
        attempts: int = 3,
        **fetch_kwargs: Any,
    ) -> tuple[str | None, Exception | None]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await self.fetch(url, headers, **fetch_kwargs), None
            except (AmazonBlockedError, AmazonRetryableError, Exception) as error:
                last_error = error
                Actor.log.warning(
                    f'{self.name} attempt {attempt}/{attempts} failed for {url}: {error}'
                )
                await self.rotate(f'{type(error).__name__} on attempt {attempt}')
                if attempt < attempts:
                    await asyncio.sleep(retry_pause_seconds(error, attempt))
        return None, last_error

    async def close(self) -> None:
        if self.http is not None:
            await self.http.close()
            self.http = None
