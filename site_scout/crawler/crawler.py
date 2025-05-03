# File: site_scout/crawler/crawler.py
"""site_scout.crawler.crawler: Асинхронный краулер с поддержкой robots.txt, retry/backoff и таймаутов."""

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
    """Асинхронный краулер драйвер с поддержкой robots.txt, лимита запросов и retry/backoff."""

    _RETRY_STATUS: Tuple[int, ...] = tuple(range(500, 600)) + (429,)

    def __init__(self, config: ScannerConfig) -> None:
        """Инициализирует AsyncCrawler с конфигурацией сканирования."""
        self.config = config
        self.logger = logging.getLogger("SiteScout")
        self.session: Optional[ClientSession] = None
        self.robots: Optional[RobotsTxtRules] = None
        self._req_times: Deque[float] = deque()
        self.fetcher: Optional[Fetcher] = None

    async def __aenter__(self) -> AsyncCrawler:
        """Открывает HTTP-сессию и загружает правила robots.txt."""
        self.session = ClientSession(
            timeout=ClientTimeout(total=self.config.timeout),
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        self.fetcher = Fetcher(self.session, self.config, self._RETRY_STATUS)

        robots_url = str(self.config.base_url).rstrip("/") + "/robots.txt"
        try:
            async with self.session.get(robots_url) as resp:
                text = await resp.text() if resp.status == 200 else ""
        except Exception as exc:
            self.logger.warning("robots.txt load error: %s", exc)
            text = ""
        self.robots = RobotsTxtRules(text)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[Exception],
        exc_tb: Optional[Any],
    ) -> None:
        """Закрывает HTTP-сессию по выходу из контекстного менеджера."""
        if self.session:
            await self.session.close()

    async def crawl(self) -> List[PageData]:
        """Выполняет BFS сканирование до max_depth/max_pages и возвращает список PageData."""
        root_url = str(self.config.base_url).rstrip("/") + "/"
        root_norm = normalize_url(root_url)
        visited: Set[str] = {root_norm}
        results: List[PageData] = []

        async with self:
            level = [(root_url, root_norm)]
            for depth in range(self.config.max_depth + 1):
                if not level or len(results) >= self.config.max_pages:
                    break
                pages = await self._crawl_level(level)
                results.extend(pages)
                if len(results) >= self.config.max_pages:
                    break
                level = self._get_next_level(pages, visited, depth)
        return results

    async def _crawl_level(self, level: List[Tuple[str, str]]) -> List[PageData]:
        """Запускает fetch для списка (URL, norm) и возвращает PageData."""
        tasks = [self._fetch_wrap(url, norm) for url, norm in level]
        return [page for page in await asyncio.gather(*tasks) if page]

    def _get_next_level(
        self,
        pages: List[PageData],
        visited: Set[str],
        depth: int,
    ) -> List[Tuple[str, str]]:
        """Фильтрует страницы и формирует следующий уровень для BFS."""
        next_level: List[Tuple[str, str]] = []
        for page in pages:
            if not isinstance(page.content, str) or depth >= self.config.max_depth:
                continue
            for link in extract_links(page):
                path = urlparse(link).path
                if self.robots and not self.robots.can_fetch(self.config.user_agent, path):
                    continue
                norm = normalize_url(link)
                if norm in visited or len(next_level) + len(visited) >= self.config.max_pages:
                    continue
                visited.add(norm)
                next_level.append((link, norm))
        return next_level

    async def _fetch_wrap(self, url: str, norm: str) -> Optional[PageData]:
        """Обёртка для метода fetcher.fetch: сохраняет нормализованный URL."""
        if not self.fetcher:
            raise RuntimeError("Fetcher not initialized")
        page = await self.fetcher.fetch(url, self.robots)
        if page:
            page.url = norm
        return page
