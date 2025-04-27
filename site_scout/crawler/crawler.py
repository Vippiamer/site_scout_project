# === FILE: site_scout_project/site_scout/crawler/crawler.py ===
"""Asynchronous crawler core for SiteScout.

Key improvements over the previous revision
-------------------------------------------
* **Robots.txt** – longest‑path match per RFC 9309, directive precedence
  implemented without order‑dependence.
* **Rate‑limit** – timestamp is advanced *before* releasing the lock, so
  concurrent workers never read a stale `_last_request_ts`.
* **URL normalisation** – trailing slash is removed **except** for the root
  path (`/`), eliminating duplicate representations of the homepage.
* **Configuration** – relies on `ScannerConfig` (no run‑time `setattr`).
  Validation merely checks presence; default values are now supplied by the
  Pydantic model.
* **Windows signals** – `add_signal_handler` wrapped in a guard (in `engine`,
  not shown here).

Public API (`PageData`, `AsyncCrawler`) is preserved.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup

__all__: Sequence[str] = ("PageData", "AsyncCrawler", "RobotsTxtRules")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PageData:
    """Simple container with fetched *url* and raw HTML *content*."""

    url: str
    content: str


# ---------------------------------------------------------------------------
# Robots.txt handling
# ---------------------------------------------------------------------------


class RobotsTxtRules:
    """Parse and evaluate robots.txt rules (RFC 9309)."""

    _Directive = Tuple[str, str]  # ("allow" | "disallow", path)

    def __init__(self, text: str) -> None:
        self._groups: List[Dict[str, object]] = []
        self._parse(text)

    # -------------------------- public API --------------------------

    def can_fetch(self, user_agent: str, path: str) -> bool:  # noqa: D401
        """Return *True* if *user_agent* may fetch *path*."""
        group = self._match_group(user_agent)
        if group is None:
            return True  # no rules ⇒ allowed

        # Pick directive with **longest matching path** (RFC 9309 §2.2.3).
        best_len = -1
        allow = True  # default when nothing matches
        for directive, rule_path in group["directives"]:  # type: ignore[index]
            if rule_path and path.startswith(rule_path):
                if len(rule_path) > best_len:
                    best_len = len(rule_path)
                    allow = directive == "allow"
        return allow

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        """Return *Crawl-delay* for *user_agent* if specified."""
        group = self._match_group(user_agent)
        return None if group is None else group["crawl_delay"]  # type: ignore[index]

    # ------------------------- internal -----------------------------

    def _parse(self, text: str) -> None:  # noqa: C901 (complexity acceptable)
        current: Optional[Dict[str, object]] = None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()  # strip comments
            if not line:
                continue
            key, _, value = line.partition(":")
            key = key.lower().strip()
            value = value.strip()

            if key == "user-agent":
                if (
                    current is None
                    or current["agents"]  # type: ignore[index]
                    and (
                        current["directives"]  # type: ignore[index]
                        or current["crawl_delay"] is not None  # type: ignore[index]
                    )
                ):
                    current = {"agents": [], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                current["agents"].append(value.lower())  # type: ignore[index]

            elif key in {"allow", "disallow"}:
                if current is None:
                    current = {"agents": ["*"], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                current["directives"].append((key, value))  # type: ignore[index]

            elif key == "crawl-delay":
                if current is None:
                    current = {"agents": ["*"], "directives": [], "crawl_delay": None}
                    self._groups.append(current)
                try:
                    current["crawl_delay"] = float(value)  # type: ignore[index]
                except ValueError:
                    continue  # ignore invalid value

    # ---------- group / UA matching (RFC 9309 §2.2.2) ---------------

    def _match_group(self, user_agent: str) -> Optional[Dict[str, object]]:
        ua = user_agent.lower()
        for group in self._groups:
            if any(self._ua_match(ua, agent) for agent in group["agents"]):  # type: ignore[index]
                return group
        # Fallback ‑ group containing "*"
        for group in self._groups:
            if "*" in group["agents"]:  # type: ignore[index]
                return group
        return None

    @staticmethod
    def _ua_match(ua: str, pattern: str) -> bool:
        pattern = pattern.lower()
        return True if pattern == "*" else ua.startswith(pattern)


# ---------------------------------------------------------------------------
# Async crawler
# ---------------------------------------------------------------------------


class AsyncCrawler:
    """High‑level asynchronous crawler.

    Parameters
    ----------
    config : ScannerConfig
        Validated configuration object.
    """

    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __init__(self, config) -> None:  # keep positional for backward compat
        self.config = config
        self._validate_config()

        # Runtime state
        self.visited: Set[str] = set()
        self.disallowed_pages: List[str] = []
        self.session: Optional[ClientSession] = None
        self.logger = logging.getLogger("SiteScout")

        # Concurrency & rate‑limit
        self._sem = asyncio.Semaphore(self.config.concurrency)
        self.rate_limit = float(self.config.rate_limit)
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0

        # Retries
        self.retry_times: int = self.config.retry_times

        # Robots
        self.robots_rules: Optional[RobotsTxtRules] = None

    # -------------------------- context manager ----------------------------

    async def __aenter__(self) -> "AsyncCrawler":
        timeout = ClientTimeout(total=self.config.timeout)
        self.session = ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        await self._load_robots()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: D401
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------------------ public --------------------------------

    async def crawl(self) -> List[PageData]:
        """Breadth‑first crawl adhering to depth & page limits."""
        self.logger.info("Старт обхода: %s", self.config.base_url)
        start_time = time.monotonic()

        queue: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()
        root = self._normalize_url(str(self.config.base_url))
        self.visited.add(root)
        await queue.put((root, 0))

        results: List[PageData] = []
        workers = [
            asyncio.create_task(self._worker(queue, results))
            for _ in range(self.config.concurrency)
        ]

        await queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        total = time.monotonic() - start_time
        self.logger.info(
            "Завершено: %d страниц за %.2f c (%.2f стр/с)",
            len(results),
            total,
            len(results) / total if total else 0.0,
        )
        if self.disallowed_pages:
            self.logger.info("Заблокировано по robots.txt: %d", len(self.disallowed_pages))
        return results

    # ------------------------------ workers -------------------------------

    async def _worker(
        self,
        queue: "asyncio.Queue[Tuple[str, int]]",
        results: List[PageData],
    ) -> None:
        while True:
            url, depth = await queue.get()
            try:
                if depth > self.config.max_depth or (
                    self.config.max_pages and len(results) >= self.config.max_pages
                ):
                    continue

                page = await self._safe_fetch(url)
                if page:
                    results.append(page)
                    if len(results) % 50 == 0:
                        self.logger.info("Собрано страниц: %d", len(results))

                    for link in await self._extract(page):
                        if link not in self.visited:
                            self.visited.add(link)
                            await queue.put((link, depth + 1))
            finally:
                queue.task_done()

    # -------------------------- HTTP fetch logic --------------------------

    async def _safe_fetch(self, url: str) -> Optional[PageData]:
        async with self._sem:
            return await self._fetch(url)

    async def _fetch(self, url: str) -> Optional[PageData]:
        if not self.session:
            raise RuntimeError("Crawler session not initialised")
        if not self._is_allowed(url):
            self.disallowed_pages.append(url)
            return None

        attempts = 0
        crawl_delay = self.robots_rules.crawl_delay(self.config.user_agent) if self.robots_rules else None

        while attempts <= self.retry_times:
            await self._wait_for_rate_limit(crawl_delay)
            start = time.monotonic()
            try:
                async with self.session.get(url) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status in self._RETRY_STATUS:
                        raise ClientError(f"Retryable status: {resp.status}")
                    if resp.status == 200 and ctype.startswith("text/html"):
                        text = await resp.text()
                        return PageData(url, text)
                    return None  # Non-HTML
            except (ClientError, asyncio.TimeoutError) as exc:
                attempts += 1
                if attempts > self.retry_times:
                    self.logger.debug("Отказ: %s (%s)", url, exc)
                    break
                backoff = min(60.0, 2 ** attempts)
                self.logger.debug("Retry %d/%d for %s after %.1fs", attempts, self.retry_times, url, backoff)
                await asyncio.sleep(backoff)
            finally:
                # Ensure Crawl-delay even when request failed fast
                elapsed = time.monotonic() - start
                if crawl_delay:
                    await asyncio.sleep(max(0.0, crawl_delay - elapsed))
        return None

    # ---------------------------- extraction ------------------------------

    async def _extract(self, page: PageData) -> List[str]:
        soup = BeautifulSoup(page.content, "html.parser")
        host = urlparse(page.url).netloc
        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if href.startswith("mailto:") or href.startswith("javascript:"):
                continue
            abs_url = self._normalize_url(urljoin(page.url, href))
            if urlparse(abs_url).netloc == host:
                links.append(abs_url)
        return links

    # ---------------------------- rate-limit ------------------------------

    async def _wait_for_rate_limit(self, crawl_delay: Optional[float]) -> None:
        min_interval = max(1.0 / self.rate_limit, crawl_delay or 0.0)
        async with self._rate_lock:
            target_time = max(self._last_request_ts + min_interval, time.monotonic())
            wait_for = target_time - time.monotonic()
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            # Reserve the next slot *before* releasing the lock
            self._last_request_ts = time.monotonic()

    # ------------------------------- helpers ------------------------------

    def _is_allowed(self, url: str) -> bool:
        return True if not self.robots_rules else self.robots_rules.can_fetch(
            self.config.user_agent, urlparse(url).path
        )

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
                    self.logger.debug("robots.txt не найден (%s): %s", resp.status, robots_url)
        except Exception as exc:  # noqa: BLE001 (best‑effort)
            self.logger.warning("Ошибка загрузки robots.txt: %s", exc)

    # ------------------------------ validation ---------------------------

    def _validate_config(self) -> None:
        required = ("base_url", "user_agent", "timeout", "max_depth", "rate_limit", "concurrency")
        for field in required:
            if not hasattr(self.config, field):
                raise AttributeError(f"config missing required attribute '{field}'")

    # --------------------------- static helpers --------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return urlunparse((scheme, netloc, path, "", "", ""))
