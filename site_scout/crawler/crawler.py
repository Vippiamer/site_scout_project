# site_scout/crawler/crawler.py
"""Asynchronous web crawler with robots.txt compliance, rate limiting, retry/backoff, and timeout handling."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import urljoin, urlparse, urlunparse

from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup

from site_scout.config import ScannerConfig

__all__ = ("PageData", "AsyncCrawler", "RobotsTxtRules")


@dataclass(slots=True)
class PageData:
    """Holds normalized URL and content of a fetched page (text or binary)."""

    url: str
    content: Union[str, bytes]


class RobotsTxtRules:
    """Parser and checker for robots.txt rules."""

    def __init__(self, text: str) -> None:
        self.groups: List[Dict[str, Any]] = []
        self._parse(text)

    def can_fetch(self, user_agent: str, path: str) -> bool:
        group = self._match_group(user_agent)
        if not group:
            return True
        allow = True
        for directive, rule in group.get("directives", []):
            if rule and path.startswith(rule):
                allow = directive == "allow"
        return allow

    def _parse(self, text: str) -> None:
        current: Optional[Dict[str, Any]] = None
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "user-agent":
                current = {"agents": [val], "directives": []}
                self.groups.append(current)
            elif key in ("allow", "disallow") and current is not None:
                # skip empty disallow (means allow all)
                if key == "disallow" and not val:
                    continue
                current["directives"].append((key, val))

    def _match_group(self, ua: str) -> Optional[Dict[str, Any]]:
        ua = ua.lower()
        for group in self.groups:
            for agent in group.get("agents", []):
                if agent == "*" or ua.startswith(agent.lower()):
                    return group
        return None


@dataclass
class AsyncCrawler:
    """Asynchronous crawler returning a list of PageData with concurrent BFS, robots.txt, rate-limit, retry/backoff, timeout."""

    config: ScannerConfig
    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __post_init__(self) -> None:
        self.logger = logging.getLogger("SiteScout")
        self._req_times: Deque[float] = deque()
        self.session: Optional[ClientSession] = None
        self.robots: Optional[RobotsTxtRules] = None

    async def __aenter__(self) -> AsyncCrawler:
        self.session = ClientSession(
            timeout=ClientTimeout(total=self.config.timeout),
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        # Load robots.txt
        base = str(self.config.base_url).rstrip("/")
        robots_url = base + "/robots.txt"
        try:
            async with self.session.get(robots_url) as resp:
                text = await resp.text() if resp.status == 200 else ""
        except Exception as exc:
            self.logger.warning("robots.txt load error: %s", exc)
            text = ""
        self.robots = RobotsTxtRules(text)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()

    async def crawl(self) -> List[PageData]:
        cfg = self.config
        self.logger.info("Starting crawl: %s", cfg.base_url)

        # Initialize root
        root_fetch = str(cfg.base_url).rstrip("/") + "/"
        root_norm = self._normalize_url(root_fetch)

        visited: Set[str] = {root_norm}
        results: List[PageData] = []

        # Start concurrent BFS
        async with self:
            current_level: List[Tuple[str, str]] = [(root_fetch, root_norm)]
            for depth in range(cfg.max_depth + 1):
                if not current_level:
                    break
                # Fetch all pages at this depth concurrently
                tasks = [self._fetch_and_wrap(fetch, norm) for fetch, norm in current_level]
                pages = await asyncio.gather(*tasks)
                next_level: List[Tuple[str, str]] = []
                for page in pages:
                    if not page:
                        continue
                    results.append(page)
                    # Enqueue child links
                    if isinstance(page.content, str) and depth < cfg.max_depth:
                        for link in self._extract_links(page):
                            parsed = urlparse(link)
                            path = parsed.path or "/"
                            if self.robots and not self.robots.can_fetch(
                                self.config.user_agent, path
                            ):
                                continue
                            norm = self._normalize_url(link)
                            if norm not in visited:
                                visited.add(norm)
                                next_level.append((link, norm))
                current_level = next_level
        return results

    async def _fetch_and_wrap(self, fetch_url: str, norm_url: str) -> Optional[PageData]:
        page = await self._fetch(fetch_url)
        if page:
            page.url = norm_url
            return page
        return None

    async def _fetch(self, url: str) -> Optional[PageData]:
        assert self.session, "Session not initialized"
        # robots.txt check
        path = urlparse(url).path or "/"
        if self.robots and not self.robots.can_fetch(self.config.user_agent, path):
            return None
        # Rate limiting (excluding root)
        base = str(self.config.base_url).rstrip("/")
        if url.rstrip("/") != base:
            now = time.monotonic()
            self._req_times.append(now)
            while self._req_times and now - self._req_times[0] > 1.0:
                self._req_times.popleft()
            if len(self._req_times) > self.config.rate_limit:
                await asyncio.sleep(1.0 - (now - self._req_times[0]))
        # Retry/backoff
        attempts = 0
        while True:
            try:
                async with self.session.get(url) as resp:
                    # Skip 404s
                    if resp.status == 404:
                        return None
                    if resp.status in self._RETRY_STATUS:
                        raise ClientError(f"Retryable status {resp.status}")
                    ctype = resp.headers.get("Content-Type", "").lower()
                    if "html" in ctype or "json" in ctype:
                        text = await resp.text()
                        return PageData(url, text)
                    data = await resp.read()
                    return PageData(url, data)
            except asyncio.TimeoutError:
                self.logger.debug("Timeout fetching %s", url)
                return None
            except ClientError:
                attempts += 1
                if attempts > self.config.retry_times:
                    self.logger.debug("Gave up %s after %d attempts", url, attempts)
                    return None
                await asyncio.sleep(min(2**attempts, 60))
        # Should not reach here
        return None

    def _extract_links(self, page: PageData) -> List[str]:
        soup = BeautifulSoup(page.content, "html.parser")  # type: ignore
        base_netloc = urlparse(page.url).netloc
        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.startswith(("mailto:", "javascript:")):
                continue
            absolute = urljoin(page.url, href)
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https") and parsed.netloc == base_netloc:
                links.append(absolute)
        return links

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            return f"{scheme}://{netloc}"
        return urlunparse((scheme, netloc, path, "", "", ""))
