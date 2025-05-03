# site_scout/crawler/fetcher.py
"""
Fetcher module: handles HTTP requests with rate limiting, retry/backoff, and timeout.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque, Optional, Sequence

from aiohttp import ClientError, ClientSession
from site_scout.config import ScannerConfig
from site_scout.crawler.models import PageData
from site_scout.crawler.robots import RobotsTxtRules


class Fetcher:
    """Handles HTTP fetching with rate limit, retries/backoff, and timeout."""

    def __init__(
        self,
        session: ClientSession,
        config: ScannerConfig,
        retry_status: Sequence[int],
    ) -> None:
        self.session = session
        self.config = config
        self._retry_status = retry_status
        self._req_times: Deque[float] = deque()

    async def fetch(self, url: str, robots: Optional[RobotsTxtRules] = None) -> PageData | None:
        """
        Fetch the URL if allowed by robots and rate limit.

        Returns PageData on success, or None on failure/denied.
        """
        # robots.txt check
        if robots:
            path = url.removeprefix(str(self.config.base_url))
            if not robots.can_fetch(self.config.user_agent, path or "/"):
                return None

        # rate limiting (excluding base URL)
        base = str(self.config.base_url).rstrip("/")
        if url.rstrip("/") != base:
            now = time.monotonic()
            self._req_times.append(now)
            # remove timestamps older than 1 second
            while self._req_times and now - self._req_times[0] > 1.0:
                self._req_times.popleft()
            if len(self._req_times) > self.config.rate_limit:
                sleep_for = 1.0 - (now - self._req_times[0])
                await asyncio.sleep(sleep_for)

        # retry/backoff loop
        attempts = 0
        while True:
            try:
                async with self.session.get(url, raise_for_status=False) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status in self._retry_status:
                        raise ClientError(f"Retryable status {resp.status}")
                    ctype = resp.headers.get("Content-Type", "").lower()
                    if "html" in ctype or "json" in ctype:
                        text = await resp.text()
                        return PageData(url, text)
                    data = await resp.read()
                    return PageData(url, data)
            except asyncio.TimeoutError:
                # no retry on timeout
                return None
            except ClientError:
                attempts += 1
                if attempts > self.config.retry_times:
                    return None
                # exponential backoff, cap at 60s
                await asyncio.sleep(min(2**attempts, 60))

        # unreachable
        return None
