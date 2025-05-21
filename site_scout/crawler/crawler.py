# === FILE: site_scout/crawler/crawler.py ===
from __future__ import annotations

import asyncio
import logging
import posixpath
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, quote, urlencode, unquote, urljoin, urlparse, urlunparse

from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup

__all__ = ("PageData", "AsyncCrawler", "RobotsTxtRules")


@dataclass(slots=True)
class PageData:
    """Результат загрузки: URL и содержание страницы."""
    url: str
    content: str


class RobotsTxtRules:
    """
    Парсит robots.txt (RFC 9309).
    Пустое Disallow считается разрешением всех путей.
    """
    _Directive = Tuple[str, str]
    _WILDCARD_RE = re.compile(r"(\*|\$)")

    def __init__(self, text: str) -> None:
        self._groups: List[Dict[str, object]] = []
        self._regex_cache: Dict[str, re.Pattern[str]] = {}
        self._parse(text)

    def can_fetch(self, user_agent: str, path: str) -> bool:
        group = self._match_group(user_agent)
        if group is None:
            return True
        best_len = -1
        allow: Optional[bool] = None
        for directive, pattern in group["directives"]:  # type: ignore[index]
            if not self._match_path(path, pattern):
                continue
            length = self._rule_len(pattern)
            if length > best_len or (length == best_len and directive == "allow" and allow is False):
                best_len = length
                allow = (directive == "allow")
        return True if allow is None else allow

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        group = self._match_group(user_agent)
        return None if group is None else group.get("crawl_delay")  # type: ignore[index]

    def _parse(self, text: str) -> None:
        current: Optional[Dict[str, object]] = None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition(":")
            key = key.lower().strip()
            val = val.strip()
            if key == "user-agent":
                if current is None or (current["agents"] and (current["directives"] or current["crawl_delay"] is not None)):
                    current = {"agents": [], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                current["agents"].append(val.lower())
            elif key == "allow":
                if current is None:
                    current = {"agents": ["*"], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                current["directives"].append(("allow", val))
            elif key == "disallow":
                # пустой Disallow разрешает все, пропускаем
                if val == "":
                    continue
                if current is None:
                    current = {"agents": ["*"], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                current["directives"].append(("disallow", val))
            elif key == "crawl-delay":
                if current is None:
                    current = {"agents": ["*"], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                try:
                    current["crawl_delay"] = float(val)
                except ValueError:
                    pass

    def _match_group(self, user_agent: str) -> Optional[Dict[str, object]]:
        ua = user_agent.lower()
        for group in self._groups:
            if any(self._ua_match(ua, a) for a in group["agents"]):  # type: ignore[index]
                return group
        for group in self._groups:
            if "*" in group["agents"]:  # type: ignore[index]
                return group
        return None

    @staticmethod
    def _ua_match(ua: str, pattern: str) -> bool:
        return pattern == "*" or ua.startswith(pattern)

    def _match_path(self, path: str, pattern: str) -> bool:
        if pattern not in self._regex_cache:
            esc = re.escape(pattern).replace(r"\*", ".*")
            if pattern.endswith("$"):
                esc = esc[:-2] + "$"
            else:
                esc += ".*"
            self._regex_cache[pattern] = re.compile(f"^{esc}")
        return bool(self._regex_cache[pattern].match(path))

    @classmethod
    def _rule_len(cls, pattern: str) -> int:
        return len(cls._WILDCARD_RE.sub("", pattern))


class AsyncCrawler:
    """Асинхронный краулер с учётом robots.txt, rate-limit и retry."""
    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __init__(self, config) -> None:
        self.config = config
        self._validate_config()
        self.retry_times: int = getattr(config, "retry_times", 2)
        self.concurrency: int = getattr(config, "concurrency", max(1, int(round(float(config.rate_limit)))))
        self.visited: Set[str] = set()
        self.disallowed_pages: List[str] = []
        self.session: Optional[ClientSession] = None
        self.logger = logging.getLogger("SiteScout")
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self.robots_rules: Optional[RobotsTxtRules] = None

    async def __aenter__(self) -> AsyncCrawler:
        timeout = ClientTimeout(total=self.config.timeout)
        self.session = ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        await self._load_robots()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def crawl(self) -> List[PageData]:
        self.logger.info("Старт обхода: %s", self.config.base_url)
        start = time.monotonic()
        queue: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()
        root = self._normalize_url(str(self.config.base_url))
        self.visited.add(root)
        await queue.put((root, 0))
        results: List[PageData] = []
        workers = [asyncio.create_task(self._worker(queue, results)) for _ in range(self.concurrency)]
        await queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        duration = time.monotonic() - start
        self.logger.info("Завершено: %d страниц за %.2f с (%.2f стр/с)", len(results), duration, len(results)/duration if duration else 0)
        if self.disallowed_pages:
            self.logger.info("Заблокировано robots.txt: %d", len(self.disallowed_pages))
        return results

    async def _worker(self, queue: asyncio.Queue[Tuple[str, int]], results: List[PageData]) -> None:
        while True:
            try:
                url, depth = await queue.get()
                if depth > self.config.max_depth or len(results) >= getattr(self.config, "max_pages", float('inf')):
                    queue.task_done()
                    continue
                page = await self._fetch(url)
                if page:
                    results.append(page)
                    if depth < self.config.max_depth:
                        for link in await self._extract(page):
                            if link not in self.visited:
                                self.visited.add(link)
                                await queue.put((link, depth+1))
                queue.task_done()
            except asyncio.CancelledError:
                break

    async def _fetch(self, url: str) -> Optional[PageData]:
        if not self.session:
            raise RuntimeError("Session not initialized")
        if not self._is_allowed(url):
            self.disallowed_pages.append(url)
            return None
        attempts = 0
        delay = self.robots_rules.crawl_delay(self.config.user_agent) if self.robots_rules else None
        while attempts <= self.retry_times:
            await self._wait_for_rate_limit(delay)
            try:
                async with self.session.get(url) as resp:
                    status = resp.status
                    mime = resp.headers.get("Content-Type", "").split(";",1)[0].lower()
                    if status in self._RETRY_STATUS:
                        raise ClientError(f"retryable status {status}")
                    if status == 200 and mime == "text/html":
                        text = await resp.text()
                        return PageData(url, text)
                    return None
            except (ClientError, asyncio.TimeoutError) as e:
                attempts += 1
                if attempts > self.retry_times:
                    self.logger.warning("Failed %s: %s", url, e)
                    break
                backoff = min(60, 2**attempts + random.random())
                self.logger.debug("Retry %d/%d for %s after %.2f s", attempts, self.retry_times, url, backoff)
                await asyncio.sleep(backoff)
        return None

    async def _extract(self, page: PageData) -> List[str]:
        soup = BeautifulSoup(page.content, "html.parser")
        host = urlparse(page.url).netloc
        links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("mailto:", "javascript:")):
                continue
            full = self._normalize_url(urljoin(page.url, href))
            if urlparse(full).netloc == host:
                links.append(full)
        return links

    async def _wait_for_rate_limit(self, crawl_delay: Optional[float]) -> None:
        interval = max(1/self.config.rate_limit, crawl_delay or 0)
        async with self._rate_lock:
            now = time.monotonic()
            wait = interval - (now - self._last_request_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _is_allowed(self, url: str) -> bool:
        return True if self.robots_rules is None else self.robots_rules.can_fetch(self.config.user_agent, urlparse(url).path)

    async def _load_robots(self) -> None:
        if not self.session:
            return
        parsed = urlparse(str(self.config.base_url))
        robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
        try:
            async with self.session.get(robots_url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    self.robots_rules = RobotsTxtRules(text)
                else:
                    # default allow all
                    self.robots_rules = None
                    self.logger.debug("robots.txt %s -> HTTP %s", robots_url, resp.status)
        except Exception as e:
            self.logger.warning("Error loading robots.txt: %s", e)
            self.robots_rules = None

    def _validate_config(self) -> None:
        required = ("base_url", "max_depth", "timeout", "user_agent", "rate_limit")
        for f in required:
            if not hasattr(self.config, f):
                raise AttributeError(f"config missing '{f}'")
        if self.config.rate_limit <= 0:
            raise ValueError("rate_limit must be > 0")

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = unquote(parsed.path or "/")
        norm = posixpath.normpath(path)
        if parsed.path.endswith("/") and not norm.endswith("/"):
            norm += "/"
        if not norm.startswith("/"):
            norm = "/" + norm
        norm = quote(norm, safe="/")
        qs = parse_qsl(parsed.query, keep_blank_values=True)
        qs.sort()
        query = urlencode(qs, doseq=True)
        return urlunparse((scheme, netloc, norm, "", query, ""))

    # alias for compatibility
    run = crawl
