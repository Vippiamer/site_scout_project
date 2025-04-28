# === FILE: site_scout/crawler/crawler.py ===
"""
Asynchronous site crawler used by **SiteScout** (type-safe, test-friendly).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Final, List, Set
from urllib.parse import urlparse, urljoin

import aiohttp

from site_scout.config import ScannerConfig
from site_scout.logger import logger
from site_scout.utils import is_valid_url, normalize_url

__all__ = ["AsyncCrawler", "Page"]


@dataclass(frozen=True)
class Page:
    """Container representing a crawled page."""

    url: str


class AsyncCrawler:
    """Simple breadth-first crawler with minimal external deps."""

    _DEFAULT_HEADERS: Final[dict[str, str]] = {"User-Agent": "SiteScout/1.0 (+https://example.com)"}

    def __init__(self, config: ScannerConfig) -> None:
        self.config: ScannerConfig = config
        self.visited: Set[str] = set()
        # seed queue with base_url as string
        self.to_visit: List[str] = [str(config.base_url)]
        # parse domain from base_url string
        self._base_domain: str = urlparse(str(config.base_url)).netloc
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> AsyncCrawler:
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self._session = aiohttp.ClientSession(timeout=timeout, headers=self._DEFAULT_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def fetch_page(self, url: str) -> str:
        """Fetch page HTML, working inside or outside context."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            async with aiohttp.ClientSession(
                timeout=timeout, headers=self._DEFAULT_HEADERS
            ) as session:
                return await self._fetch_with_retry(session, url)
        return await self._fetch_with_retry(self._session, url)

    async def crawl(self, session: aiohttp.ClientSession | None = None) -> List[Page]:
        """Perform BFS crawl, returning list of Page objects."""
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
                if is_valid_url(n_link, self._base_domain) and n_link not in self.visited:
                    self.to_visit.append(n_link)
        # wrap visited URLs as normalized Page instances without trailing slash
        pages: List[Page] = []
        for u in self.visited:
            # Strip any trailing slash for consistency
            stripped = u.rstrip("/")
            pages.append(Page(url=stripped))
        return pages

    async def _fetch_with_retry(self, session: aiohttp.ClientSession, url: str) -> str:
        """Fetch a URL with retry on server errors."""
        attempts = 0
        retries = self.config.retry_times
        while attempts <= retries:
            try:
                async with session.get(url) as resp:
                    if resp.status >= 500:
                        attempts += 1
                        continue
                    return await resp.text()
            except Exception as exc:
                logger.error("Error fetching %s: %s", url, exc)
                attempts += 1
        # if all retries failed, return empty content
        return ""

    async def _fetch_page(self, url: str) -> str:
        assert self._session is not None
        return await self._fetch_with_retry(self._session, url)

    def _extract_links(self, content: str) -> List[str]:
        # Extract href attributes and resolve relative URLs
        raw_links = re.findall(r'href=["\']([^"\']+)["\']', content)
        return [urljoin(str(self.config.base_url), link) for link in raw_links]

    async def start(self) -> None:
        async with self as crawler:
            await crawler.crawl()

    def start_scan(self) -> None:
        asyncio.run(self.start())

    def __repr__(self) -> str:  # pragma: no cover
        return f"AsyncCrawler(visited={len(self.visited)}, queue={len(self.to_visit)})"
