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
    """Holds URL and content of a fetched page (text or binary)."""

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
        for directive, rule_path in group.get("directives", []):
            if path.startswith(rule_path):
                allow = directive == "allow"
        return allow

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        group = self._match_group(user_agent)
        return group.get("crawl_delay") if group else None

    def _parse(self, text: str) -> None:
        current: Optional[Dict[str, Any]] = None
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, value = line.partition(":")
            key, value = key.lower().strip(), value.strip()
            if key == "user-agent":
                current = {"agents": [value], "directives": [], "crawl_delay": None}
                self.groups.append(current)
            elif key in ("allow", "disallow") and current:
                current["directives"].append((key, value))
            elif key == "crawl-delay" and current:
                try:
                    current["crawl_delay"] = float(value)
                except ValueError:
                    pass

    def _match_group(self, user_agent: str) -> Optional[Dict[str, Any]]:
        ua = user_agent.lower()
        for group in self.groups:
            for agent in group.get("agents", []):
                if agent == "*" or ua.startswith(agent.lower()):
                    return group
        return None


@dataclass
class AsyncCrawler:
    """Asynchronous crawler returning List of PageData. Supports async context manager."""

    config: ScannerConfig

    # Status codes that should trigger retry
    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __post_init__(self) -> None:
        self.logger = logging.getLogger("SiteScout")
        self.session: Optional[ClientSession] = None
        self.robots_rules: Optional[RobotsTxtRules] = None
        self._rate_lock = asyncio.Lock()
        self._req_times: Deque[float] = deque()

    async def __aenter__(self) -> AsyncCrawler:
        timeout = ClientTimeout(total=self.config.timeout)
        self.session = ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        # Load robots.txt
        parsed = urlparse(str(self.config.base_url))
        robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
        try:
            async with self.session.get(robots_url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    self.robots_rules = RobotsTxtRules(text)
        except Exception as exc:
            self.logger.warning("robots.txt load error: %s", exc)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            await self.session.close()

    async def crawl(self) -> List[PageData]:
        """Breadth-first crawl up to max_depth, including root page."""
        cfg = self.config
        self.logger.info("Starting crawl: %s", cfg.base_url)

        # Normalize root URL for storage and prepare fetch URL with trailing slash
        root_norm = self._normalize_url(str(cfg.base_url))
        fetch_root = str(cfg.base_url).rstrip("/") + "/"

        results: List[PageData] = []
        visited: Set[str] = {root_norm}
        queue: Deque[Tuple[str, int]] = deque([(fetch_root, 0)])

        # Use session opened via context manager
        while queue:
            url, depth = queue.popleft()
            if depth > cfg.max_depth:
                continue
            page = await self._fetch(url)
            if not page:
                continue
            # Assign normalized URL
            page.url = self._normalize_url(url)
            results.append(page)
            # Enqueue links
            if isinstance(page.content, str) and depth < cfg.max_depth:
                for link in self._extract_links(page):
                    if link not in visited:
                        visited.add(link)
                        queue.append((link, depth + 1))
        return results

    async def _fetch(self, url: str) -> Optional[PageData]:
        """Fetch a single page respecting robots rules, rate-limit, timeout, and retry."""
        if not self.session:
            raise RuntimeError("Session not initialized")
        # Robots check
        path = urlparse(url).path
        if self.robots_rules and not self.robots_rules.can_fetch(self.config.user_agent, path):
            self.logger.debug("Blocked by robots: %s", url)
            return None
        # Rate limiting
        await self._respect_rate()

        attempts = 0
        while True:
            try:
                async with self.session.get(url) as resp:
                    if resp.status in self._RETRY_STATUS:
                        raise ClientError(f"Retryable status {resp.status}")
                    ctype = resp.headers.get("Content-Type", "").lower()
                    if "html" in ctype or "json" in ctype:
                        text = await resp.text()
                        return PageData(url, text)
                    if "application/pdf" in ctype:
                        data = await resp.read()
                        return PageData(url, data)
                    # Fallback
                    try:
                        text = await resp.text()
                        return PageData(url, text)
                    except Exception:
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
                backoff = min(2**attempts, 60)
                await asyncio.sleep(backoff)

    async def _respect_rate(self) -> None:
        """Ensure no more than rate_limit requests per second."""
        now = time.monotonic()
        self._req_times.append(now)
        while self._req_times and now - self._req_times[0] > 1:
            self._req_times.popleft()
        if len(self._req_times) > self.config.rate_limit:
            await asyncio.sleep(1 - (now - self._req_times[0]))

    def _extract_links(self, page: PageData) -> List[str]:
        """Extract and normalize internal links from HTML content."""
        soup = BeautifulSoup(page.content, "html.parser")  # type: ignore
        base_netloc = urlparse(page.url).netloc
        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if href.startswith(("mailto:", "javascript:")):
                continue
            full = self._normalize_url(urljoin(page.url, href))
            if urlparse(full).netloc == base_netloc:
                links.append(full)
        return links

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL by lowercasing scheme/netloc and removing trailing slash for root."""
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or ""
        normalized = path.rstrip("/") or "/"
        if normalized == "/":
            return f"{scheme}://{netloc}"
        return urlunparse((scheme, netloc, normalized, "", "", ""))
