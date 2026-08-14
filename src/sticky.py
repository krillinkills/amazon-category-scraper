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
    polite_pause,
)

IMPERSONATE_POOL = (
    'chrome',
    'chrome131',
    'chrome136',
    'chrome146',
    'safari184',
    'edge101',
)
DEFAULT_IMPERSONATE = 'chrome'
MAX_REQUESTS_PER_IP = 25
LISTING_REQUESTS_PER_IP = 15


class StickyProxySession:
    def __init__(
        self,
        proxy_configuration: Any | None,
        *,
        name: str,
        max_requests: int = MAX_REQUESTS_PER_IP,
    ) -> None:
        self.proxy_configuration = proxy_configuration
        self.name = name
        self.max_requests = max_requests
        self.session_id: str | None = None
        self.http: AsyncSession | None = None
        self.requests_on_ip = 0
        self.rotations = 0

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
        if reason != 'start':
            Actor.log.info(f'Rotated sticky IP {self.name} -> {self.session_id} ({reason})')

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
                    if isinstance(error, AmazonBlockedError):
                        await polite_pause(0.6, 1.4)
                    else:
                        await polite_pause(0.15, 0.5)
        return None, last_error

    async def close(self) -> None:
        if self.http is not None:
            await self.http.close()
            self.http = None
