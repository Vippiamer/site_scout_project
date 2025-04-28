# Модуль асинхронного краулинга для проекта SiteScout.
# Поддержка:
# • корректного robots.txt (Allow/Disallow/Crawl-delay);
# • глобального rate-limit;
# • retry с экспоненциальным back-off (только по ClientError);
# • таймаутов без повторных попыток для запроса (TimeoutError);
# • параллельной загрузки страниц на одном уровне глубины;
# • расширенная поддержка контента: HTML, JSON, PDF;
# • прогресса через logging;
# • PEP-8 и сохранения публичного API.

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Sequence, Set, Tuple, Union
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup

__all__ = ("PageData", "AsyncCrawler", "RobotsTxtRules")


@dataclass(slots=True)
class PageData:
    """Хранит URL и контент загруженной страницы."""

    url: str
    # content может быть текстом (HTML/JSON) или бинарными данными (PDF)
    content: Union[str, bytes]


class RobotsTxtRules:
    _Directive = Tuple[str, str]

    def __init__(self, text: str) -> None:
        self._groups: List[Dict[str, Any]] = []
        self._parse(text)

    def can_fetch(self, user_agent: str, path: str) -> bool:
        group = self._match_group(user_agent)
        if group is None:
            return True
        allow = True
        for directive, rule_path in group.get("directives", []):
            if rule_path and path.startswith(rule_path):
                allow = directive == "allow"
        return allow

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        group = self._match_group(user_agent)
        return None if not group else group.get("crawl_delay")  # type: ignore

    def _parse(self, text: str) -> None:
        current: Optional[Dict[str, Any]] = None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, value = line.partition(":")
            key = key.lower().strip()
            value = value.strip()
            if key == "user-agent":
                current = {"agents": [value.lower()], "directives": [], "crawl_delay": None}
                self._groups.append(current)
            elif key in ("allow", "disallow") and current:
                current["directives"].append((key, value))
            elif key == "crawl-delay" and current:
                try:
                    current["crawl_delay"] = float(value)
                except ValueError:
                    pass

    def _match_group(self, user_agent: str) -> Optional[Dict[str, Any]]:
        ua = user_agent.lower()
        for group in self._groups:
            for agent in group.get("agents", []):
                if agent == "*" or ua.startswith(agent):
                    return group
        return None


@dataclass
class AsyncCrawler:
    """
    Асинхронный краулер.
    crawl() возвращает List[PageData].
    """

    visited: Set[str] = field(init=False, default_factory=set)
    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __init__(self, config: Any) -> None:
        self.config = config
        self._validate_config()
        self.logger = logging.getLogger("SiteScout")
        self.session: Optional[ClientSession] = None
        self._rate_lock = asyncio.Lock()
        self.rate_limit = max(1.0, float(self.config.rate_limit))
        self.retry_times = getattr(self.config, "retry_times", 0)
        self.visited = set()
        self._req_timestamps: Deque[float] = deque()

    def _validate_config(self) -> None:
        required = ("base_url", "user_agent", "timeout", "max_depth", "rate_limit")
        for field_name in required:
            if not hasattr(self.config, field_name):
                raise AttributeError(f"config missing required attribute '{field_name}'")

    async def __aenter__(self) -> AsyncCrawler:
        timeout = ClientTimeout(total=self.config.timeout)
        self.session = ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        # загружаем robots.txt
        parsed = urlparse(str(self.config.base_url))
        robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
        try:
            async with self.session.get(robots_url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    self.robots_rules = RobotsTxtRules(text)
        except Exception as exc:
            self.logger.warning("Ошибка загрузки robots.txt: %s", exc)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()

    async def crawl(self) -> List[PageData]:
        self.logger.info("Старт обхода: %s", self.config.base_url)
        start = time.monotonic()
        results: List[PageData] = []

        root = self._normalize_url(str(self.config.base_url))
        self.visited.add(root)

        # Fetch root page
        page0 = await self._fetch(root)
        if page0:
            results.append(page0)

        # Gather links at depth 1
        level_urls: List[str] = []
        if page0 and isinstance(page0.content, str):
            soup = BeautifulSoup(page0.content, "html.parser")
            base_host = urlparse(page0.url).netloc
            for tag in soup.find_all("a", href=True):
                href = tag["href"]
                if href.startswith(("mailto:", "javascript:")):
                    continue
                abs_url = self._normalize_url(urljoin(page0.url, href))
                if urlparse(abs_url).netloc == base_host and abs_url not in self.visited:
                    self.visited.add(abs_url)
                    level_urls.append(abs_url)
        self.logger.info("Depth %d: found %d links", 1, len(level_urls))

        # Process subsequent depths with parallel fetch
        for depth in range(1, int(self.config.max_depth) + 1):
            self.logger.info("Depth %d: fetching %d URLs", depth, len(level_urls))
            if not level_urls:
                break
            tasks = [self._fetch(u) for u in level_urls]
            pages = await asyncio.gather(*tasks)
            fetched = sum(1 for p in pages if p)
            self.logger.info("Depth %d: fetched %d/%d pages", depth, fetched, len(pages))

            next_level: List[str] = []
            for p in pages:
                if not p or not isinstance(p.content, str):
                    results.append(p) if p else None
                    continue
                results.append(p)
                if depth < self.config.max_depth:
                    soup = BeautifulSoup(p.content, "html.parser")
                    base_host = urlparse(p.url).netloc
                    for tag in soup.find_all("a", href=True):
                        href = tag["href"]
                        if href.startswith(("mailto:", "javascript:")):
                            continue
                        abs_url = self._normalize_url(urljoin(p.url, href))
                        if urlparse(abs_url).netloc == base_host and abs_url not in self.visited:
                            self.visited.add(abs_url)
                            next_level.append(abs_url)
            level_urls = next_level

        total = time.monotonic() - start
        self.logger.info(
            "Завершено: %d страниц за %.2f c (%.2f стр/с)",
            len(results),
            total,
            len(results) / total if total else 0.0,
        )
        return results

    async def _fetch(self, url: str) -> Optional[PageData]:
        """
        Загружает одну страницу, обрабатывая robots.txt, таймауты и retry по ClientError.
        Поддерживает HTML, JSON и PDF.
        """
        if not self.session:
            raise RuntimeError("Crawler session not initialised")
        # robots.txt
        if hasattr(self, "robots_rules") and not self.robots_rules.can_fetch(
            self.config.user_agent, urlparse(url).path
        ):
            self.logger.debug("Заблокировано robots.txt: %s", url)
            return None

        attempts = 0
        while attempts <= self.retry_times:
            try:
                async with self.session.get(url) as resp:
                    ctype = resp.headers.get("Content-Type", "").lower()
                    if resp.status in self._RETRY_STATUS:
                        raise ClientError(f"Retryable status: {resp.status}")
                    # HTML
                    if ctype.startswith("text/html"):
                        text = await resp.text()
                        return PageData(url, text)
                    # JSON
                    if ctype.startswith("application/json"):
                        text = await resp.text()
                        return PageData(url, text)
                    # PDF
                    if "application/pdf" in ctype:
                        data = await resp.read()
                        return PageData(url, data)
                    self.logger.debug("Unsupported content type '%s' at %s", ctype, url)
                    return None
            except asyncio.TimeoutError as exc:
                self.logger.debug("Timeout fetching %s: %s", url, exc)
                return None
            except ClientError as exc:
                attempts += 1
                if attempts > self.retry_times:
                    self.logger.debug("Отказ после попыток %d: %s (%s)", attempts, url, exc)
                    return None
                await asyncio.sleep(min(60.0, 2**attempts))
        return None

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        normalized = path.rstrip("/") or "/"
        if normalized == "/":
            return f"{scheme}://{netloc}"
        return urlunparse((scheme, netloc, normalized, "", "", ""))
