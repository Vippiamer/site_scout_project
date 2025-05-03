# site_scout/crawler/crawler.py
"""AsyncCrawler orchestrator: manages BFS crawl using modular components."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Deque, List, Optional, Set, Tuple
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout
from site_scout.config import ScannerConfig
from site_scout.crawler.fetcher import Fetcher
from site_scout.crawler.link_extractor import extract_links, normalize_url
from site_scout.crawler.models import PageData
from site_scout.crawler.robots import RobotsTxtRules

__all__ = ("PageData", "AsyncCrawler", "RobotsTxtRules")


class AsyncCrawler:
    """Asynchronous crawler driver with robots.txt, rate-limit, retry/backoff, timeout."""

    _RETRY_STATUS: Tuple[int, ...] = tuple(range(500, 600)) + (429,)

    def __init__(self, config: ScannerConfig) -> None:
        self.config = config
        self.logger = logging.getLogger("SiteScout")
        self.session: Optional[ClientSession] = None
        self.robots: Optional[RobotsTxtRules] = None
        self._req_times: Deque[float] = deque()
        self.fetcher: Optional[Fetcher] = None

    async def __aenter__(self) -> AsyncCrawler:
        session = ClientSession(
            timeout=ClientTimeout(total=self.config.timeout),
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        self.session = session
        self.fetcher = Fetcher(session, self.config, self._RETRY_STATUS)

        # Load robots.txt
        base = str(self.config.base_url).rstrip("/")
        robots_url = base + "/robots.txt"
        try:
            async with session.get(robots_url) as resp:
                text = await resp.text() if resp.status == 200 else ""
        except Exception as exc:
            self.logger.warning("robots.txt load error: %s", exc)
            text = ""
        self.robots = RobotsTxtRules(text)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        if self.session:
            await self.session.close()

    async def crawl(self) -> List[PageData]:
        """Perform BFS crawl up to max_depth/max_pages, returning all PageData."""
        cfg = self.config
        self.logger.info("Starting crawl: %s", cfg.base_url)

        root = str(cfg.base_url).rstrip("/") + "/"
        root_norm = normalize_url(root)

        visited: Set[str] = {root_norm}
        results: List[PageData] = []

        async with self:
            level: List[Tuple[str, str]] = [(root, root_norm)]

            for depth in range(cfg.max_depth + 1):
                if not level or len(results) >= cfg.max_pages:
                    break
                tasks = [self._fetch_wrap(url, norm) for url, norm in level]
                pages = await asyncio.gather(*tasks)
                next_level: List[Tuple[str, str]] = []

                for page in pages:
                    if not page:
                        continue
                    results.append(page)
                    if isinstance(page.content, str) and depth < cfg.max_depth:
                        for link in extract_links(page):
                            path = urlparse(link).path
                            if not self.robots or self.robots.can_fetch(cfg.user_agent, path):
                                norm = normalize_url(link)
                                if norm not in visited and len(results) < cfg.max_pages:
                                    visited.add(norm)
                                    next_level.append((link, norm))
                level = next_level
        return results

    async def _fetch_wrap(self, url: str, norm: str) -> Optional[PageData]:
        assert self.fetcher, "Fetcher not initialized"
        page = await self.fetcher.fetch(url, self.robots)
        if page:
            page.url = norm
        return page
