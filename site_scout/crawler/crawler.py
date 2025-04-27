# === FILE: site_scout_project/site_scout/crawler/crawler.py ===
"""
Asynchronous site crawler used by **SiteScout** (type-safe, test-friendly).
"""
from __future__ import annotations

import asyncio
import json
from typing import Final, List, Set
from urllib.parse import urlparse

import aiohttp

from site_scout.config import ScannerConfig
from site_scout.logger import logger
from site_scout.utils import is_valid_url, normalize_url

__all__ = ["AsyncCrawler"]


class AsyncCrawler:
    """Simple breadth-first crawler with minimal external deps."""

    _DEFAULT_HEADERS: Final[dict[str, str]] = {"User-Agent": "SiteScout/1.0 (+https://example.com)"}

    # ------------------------------------------------------------------#
    # construction                                                      #
    # ------------------------------------------------------------------#
    def __init__(self, config: ScannerConfig) -> None:
        self.config: ScannerConfig = config
        self.visited: Set[str] = set()
        self.to_visit: List[str] = [config.base_url]

        self._base_domain: str = urlparse(config.base_url).netloc
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------#
    # async context-manager helpers                                     #
    # ------------------------------------------------------------------#
    async def __aenter__(self) -> "AsyncCrawler":
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self._session = aiohttp.ClientSession(timeout=timeout, headers=self._DEFAULT_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------#
    # public API expected by engine/tests                               #
    # ------------------------------------------------------------------#
    async def fetch_page(self, url: str) -> str:
        """Public wrapper usable without an opened context."""
        if self._session is None:  # stand-alone call
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            async with aiohttp.ClientSession(
                timeout=timeout, headers=self._DEFAULT_HEADERS
            ) as session:
                try:
                    async with session.get(url) as resp:
                        return await resp.text()
                except Exception as exc:  # pragma: no cover
                    logger.error("Error fetching %s: %s", url, exc)
                    return ""
        # session already exists
        return await self._fetch_page(url)

    async def crawl(self, session: aiohttp.ClientSession | None = None) -> List[str]:
        if session is not None:
            self._session = session
        if self._session is None:
            raise RuntimeError("No aiohttp session available for crawling")

        max_pages = self.config.max_pages
        while self.to_visit and len(self.visited) < max_pages:
            url = self.to_visit.pop(0)
            if url in self.visited:
                continue

            self.visited.add(url)
            content = await self._fetch_page(url)

            for link in self._extract_links(content):
                n_link = normalize_url(link)
                if is_valid_url(n_link, self._base_domain):
                    self.to_visit.append(n_link)
        return list(self.visited)

    # ------------------------------------------------------------------#
    # internal helpers                                                  #
    # ------------------------------------------------------------------#
    async def _fetch_page(self, url: str) -> str:
        assert self._session is not None  # guarded by callers
        try:
            async with self._session.get(url) as resp:
                return await resp.text()
        except Exception as exc:  # pragma: no cover
            logger.error("Error fetching %s: %s", url, exc)
            return ""

    def _extract_links(self, content: str) -> List[str]:
        # Minimal stub – extend with real HTML parsing later
        return []

    # ------------------------------------------------------------------#
    # convenience wrappers                                              #
    # ------------------------------------------------------------------#
    async def start(self) -> None:
        async with self as crawler:
            await crawler.crawl()

    def start_scan(self) -> None:
        asyncio.run(self.start())

    # ------------------------------------------------------------------#
    # debug helper                                                      #
    # ------------------------------------------------------------------#
    def __repr__(self) -> str:  # pragma: no cover
        return json.dumps({"visited": len(self.visited), "queue": len(self.to_visit)})
