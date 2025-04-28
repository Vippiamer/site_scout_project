# Модуль асинхронного краулинга для проекта SiteScout.
# Поддержка:
# • корректного robots.txt (Allow/Disallow/Crawl-delay);
# • глобального rate-limit;
# • retry с экспоненциальным back-off;
# • таймаутов, прогресса через logging;
# • PEP-8 и сохранения публичного API.

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup

__all__ = ("PageData", "AsyncCrawler", "RobotsTxtRules")


@dataclass(slots=True)
class PageData:
    """Хранит URL и контент загруженной страницы."""

    url: str
    content: str


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
    crawl() отдаёт List[PageData].
    """

    # Модельный атрибут для хранения посещённых URL; инициализируется в __init__
    visited: Set[str] = field(init=False, default_factory=set)

    # HTTP-статусы, при которых следует повторить попытку
    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __init__(self, config: Any) -> None:
        self.config = config
        self._validate_config()
        self.logger = logging.getLogger("SiteScout")
        self.session: Optional[ClientSession] = None
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self.rate_limit = max(1.0, float(self.config.rate_limit))
        self.retry_times = getattr(self.config, "retry_times", 0)
        # Явно обнуляем посещённые URL перед обходом
        self.visited.clear()

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
        # сбрасываем посещённые URL перед каждым новым обходом
        self.visited.clear()
        queue: Deque[Tuple[str, int]] = deque()
        root = self._normalize_url(str(self.config.base_url))
        self.visited.add(root)
        queue.append((root, 0))

        while queue:
            url, depth = queue.popleft()
            if depth > self.config.max_depth:
                continue
            page_data = await self._fetch(url)
            if not page_data:
                continue
            results.append(page_data)
            soup = BeautifulSoup(page_data.content, "html.parser")
            base_host = urlparse(page_data.url).netloc
            for tag in soup.find_all("a", href=True):
                href = tag["href"]
                if href.startswith(("mailto:", "javascript:")):
                    continue
                abs_url = self._normalize_url(urljoin(page_data.url, href))
                if urlparse(abs_url).netloc == base_host and abs_url not in self.visited:
                    self.visited.add(abs_url)
                    queue.append((abs_url, depth + 1))
        total = time.monotonic() - start
        self.logger.info(
            "Завершено: %d страниц за %.2f c (%.2f стр/с)",
            len(results),
            total,
            len(results) / total if total else 0.0,
        )
        return results

    async def _fetch(self, url: str) -> Optional[PageData]:
        if not self.session:
            raise RuntimeError("Crawler session not initialised")
        if hasattr(self, "robots_rules") and not self.robots_rules.can_fetch(
            self.config.user_agent, urlparse(url).path
        ):
            self.logger.debug("Заблокировано robots.txt: %s", url)
            return None
        async with self._rate_lock:
            now = time.monotonic()
            wait = 1.0 / self.rate_limit - (now - self._last_request_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_ts = time.monotonic()
        attempts = 0
        while attempts <= self.retry_times:
            try:
                async with self.session.get(url) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status in self._RETRY_STATUS:
                        raise ClientError(f"Retryable status: {resp.status}")
                    if resp.status == 200 and ctype.startswith("text/html"):
                        text = await resp.text()
                        return PageData(url, text)
                    return None
            except (ClientError, asyncio.TimeoutError) as exc:
                attempts += 1
                if attempts > self.retry_times:
                    self.logger.debug("Отказ: %s (%s)", url, exc)
                    return None
                await asyncio.sleep(min(60.0, 2**attempts))
        return None

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        normalized_path = path.rstrip("/") or "/"
        return urlunparse((scheme, netloc, normalized_path, "", "", ""))
