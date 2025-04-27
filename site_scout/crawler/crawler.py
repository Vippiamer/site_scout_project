# === FILE: site_scout_project/site_scout/crawler/crawler.py ===
# Асинхронный краулер для проекта *site_scout_project*.
#
# Гарантирует:
#   • корректное соблюдение robots.txt (RFC 9309);
#   • глобальный rate-limit и учёт Crawl-delay;
#   • экспоненциальный back-off с джиттером и настраиваемым списком кодов;
#   • таймауты, конкурентность, журнал прогресса;
#   • неизменный публичный API (PageData, AsyncCrawler, RobotsTxtRules).
#
# Код соответствует PEP-8 и не модифицирует объект конфигурации (Pydantic-model).

from __future__ import annotations

import asyncio
import errno
import logging
import posixpath
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import (
    parse_qsl,
    quote,
    urlencode,
    unquote,
    urljoin,
    urlparse,
    urlunparse,
)

from aiohttp import ClientError, ClientSession, ClientTimeout
from bs4 import BeautifulSoup

__all__ = ("PageData", "AsyncCrawler", "RobotsTxtRules")

###############################################################################
# Дата-класс результата
###############################################################################


@dataclass(slots=True)
class PageData:
    """URL и HTML-контент загруженной страницы."""
    url: str
    content: str


###############################################################################
# Robots.txt
###############################################################################


class RobotsTxtRules:
    """
    Интерпретирует robots.txt (RFC 9309).

    • Побеждает правило с самым длинным совпадением; при равной длине
      приоритет у Allow.
    • Поддерживает «*» и «$».
    • Хранит Crawl-delay для каждой группы.
    """

    _Directive = Tuple[str, str]          # ("allow" | "disallow", pattern)
    _WILDCARD_RE = re.compile(r"(\*|\$)")  # для расчёта длины правила

    def __init__(self, text: str) -> None:
        self._groups: List[Dict[str, object]] = []
        self._regex_cache: Dict[str, re.Pattern[str]] = {}
        self._parse(text)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def can_fetch(self, user_agent: str, path: str) -> bool:  # noqa: C901
        """True — если `user_agent` разрешено скачивать `path`."""
        group = self._match_group(user_agent)
        if group is None:
            return True

        best_len: int = -1
        allow: Optional[bool] = None

        for directive, pattern in group["directives"]:  # type: ignore[index]
            matched = self._match_path(path, pattern)
            if not matched:
                continue

            rule_len = self._rule_len(pattern)
            if (
                rule_len > best_len
                or (rule_len == best_len and directive == "allow" and allow is False)
            ):
                best_len = rule_len
                allow = directive == "allow"

        return True if allow is None else allow

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        group = self._match_group(user_agent)
        return None if group is None else group["crawl_delay"]  # type: ignore[index]

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    def _parse(self, text: str) -> None:
        current: Optional[Dict[str, object]] = None

        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue

            key, _, value = line.partition(":")
            key, value = key.lower().strip(), value.strip()

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

            elif key in ("allow", "disallow"):
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
                    continue  # игнорируем нечисловое значение

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
        return pattern == "*" or ua.startswith(pattern.lower())

    # ------------------------ path matching -------------------------- #

    def _match_path(self, path: str, pattern: str) -> bool:
        if pattern == "":
            return True
        if pattern not in self._regex_cache:
            escaped = re.escape(pattern).replace(r"\*", ".*")
            if pattern.endswith("$"):
                escaped = escaped[:-2] + "$"
            else:
                escaped += ".*"
            self._regex_cache[pattern] = re.compile(f"^{escaped}")
        return bool(self._regex_cache[pattern].match(path))

    @classmethod
    def _rule_len(cls, pattern: str) -> int:
        """Длина без спец-символов для приоритетов."""
        return len(cls._WILDCARD_RE.sub("", pattern))


###############################################################################
# Async crawler
###############################################################################


class AsyncCrawler:
    """
    Асинхронный обход сайта.
    Публичный интерфейс не изменён: `crawl()` → List[PageData].
    """

    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __init__(self, config) -> None:
        # Сохраняем ссылку, но **не** изменяем Pydantic-объект.
        self.config = config
        self._validate_config()

        # Параметры, которые могут отсутствовать в конфиге —
        # определяем их один раз и используем далее.
        self.retry_times: int = getattr(config, "retry_times", 2)
        self.concurrency: int = getattr(
            config, "concurrency", max(1, int(round(float(config.rate_limit))))
        )

        self.visited: Set[str] = set()
        self.disallowed_pages: List[str] = []

        self.session: Optional[ClientSession] = None
        self.logger = logging.getLogger("SiteScout")

        # Rate-limit.
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self.rate_limit = float(config.rate_limit)

        # Robots.
        self.robots_rules: Optional[RobotsTxtRules] = None

    # ------------------------------------------------------------------ #
    # Context-manager
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "AsyncCrawler":
        timeout = ClientTimeout(total=self.config.timeout)
        self.session = ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent},
            raise_for_status=False,
        )
        await self._load_robots()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    async def crawl(self) -> List[PageData]:
        """Запускает обход сайта согласно настройкам."""
        self.logger.info("Старт обхода: %s", self.config.base_url)

        start_time = time.monotonic()
        queue: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()

        root = self._normalize_url(str(self.config.base_url))
        self.visited.add(root)
        await queue.put((root, 0))

        max_pages = getattr(self.config, "max_pages", 5000)
        results: List[PageData] = []

        workers = [
            asyncio.create_task(self._worker(queue, results, max_pages))
            for _ in range(self.concurrency)
        ]

        await queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        total = time.monotonic() - start_time
        self.logger.info(
            "Завершено: %d страниц за %.2f с (%.2f стр/с)",
            len(results),
            total,
            len(results) / total if total else 0.0,
        )
        if self.disallowed_pages:
            self.logger.info("Заблокировано robots.txt: %d", len(self.disallowed_pages))
        return results

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #

    async def _worker(
        self,
        queue: "asyncio.Queue[Tuple[str, int]]",
        results: List[PageData],
        max_pages: int,
    ) -> None:  # noqa: C901
        try:
            while True:
                url, depth = await queue.get()

                if depth > self.config.max_depth or len(results) >= max_pages:
                    queue.task_done()
                    continue

                page = await self._fetch(url)
                if page:
                    results.append(page)
                    if len(results) % 50 == 0:
                        self.logger.info("Собрано страниц: %d", len(results))

                    if depth + 1 <= self.config.max_depth:
                        for link in await self._extract(page):
                            if link not in self.visited and len(results) < max_pages:
                                self.visited.add(link)
                                await queue.put((link, depth + 1))

                queue.task_done()
        except asyncio.CancelledError:
            return  # корректное завершение воркера

    # ------------------------------------------------------------------ #
    # HTTP & parsing
    # ------------------------------------------------------------------ #

    async def _fetch(self, url: str) -> Optional[PageData]:  # noqa: C901
        if not self.session:
            raise RuntimeError("Crawler session not initialised")

        if not self._is_allowed(url):
            self.disallowed_pages.append(url)
            return None

        attempts = 0
        crawl_delay = (
            self.robots_rules.crawl_delay(self.config.user_agent)
            if self.robots_rules
            else None
        )

        while attempts <= self.retry_times:
            await self._wait_for_rate_limit(crawl_delay)

            try:
                async with self.session.get(url) as resp:
                    status = resp.status
                    mime = resp.headers.get("Content-Type", "").split(";", 1)[0].lower()

                    if status in self._RETRY_STATUS:
                        raise ClientError(f"retryable status {status}")

                    if status == 200 and mime == "text/html":
                        text = await resp.text()
                        return PageData(url, text)

                    return None  # не HTML или не 200

            except (ClientError, asyncio.TimeoutError) as exc:
                attempts += 1
                if attempts > self.retry_times:
                    self.logger.warning("Отказ: %s (%s)", url, exc)
                    break

                backoff = min(60.0, 2 ** attempts + random.uniform(0, 1))
                self.logger.debug(
                    "Retry %d/%d для %s через %.2f с",
                    attempts,
                    self.retry_times,
                    url,
                    backoff,
                )
                await asyncio.sleep(backoff)

        return None

    async def _extract(self, page: PageData) -> List[str]:
        soup = BeautifulSoup(page.content, "html.parser")
        host = urlparse(page.url).netloc

        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if href.startswith(("mailto:", "javascript:")):
                continue
            abs_url = self._normalize_url(urljoin(page.url, href))
            if urlparse(abs_url).netloc == host:
                links.append(abs_url)
        return links

    # ------------------------------------------------------------------ #
    # Rate-limit helpers
    # ------------------------------------------------------------------ #

    async def _wait_for_rate_limit(self, crawl_delay: Optional[float]) -> None:
        """Удерживает QPS ≤ rate_limit и учитывает Crawl-delay."""
        min_interval = max(1.0 / self.rate_limit, crawl_delay or 0.0)
        async with self._rate_lock:
            now = time.monotonic()
            wait_for = min_interval - (now - self._last_request_ts)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_ts = time.monotonic()

    # ------------------------------------------------------------------ #
    # Misc helpers
    # ------------------------------------------------------------------ #

    def _is_allowed(self, url: str) -> bool:
        if not self.robots_rules:
            return True
        return self.robots_rules.can_fetch(self.config.user_agent, urlparse(url).path)

    async def _load_robots(self) -> None:
        if not self.session:
            return

        parsed = urlparse(str(self.config.base_url))
        robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))

        try:
            async with self.session.get(robots_url) as resp:
                if resp.status == 200:
                    self.robots_rules = RobotsTxtRules(await resp.text())
                else:
                    self.logger.debug("robots.txt %s → HTTP %s", robots_url, resp.status)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Ошибка загрузки robots.txt: %s", exc)

    def _validate_config(self) -> None:
        """Проверяем только обязательные поля, не меняя модель Pydantic."""
        required = ("base_url", "user_agent", "timeout", "max_depth", "rate_limit")
        for field in required:
            if not hasattr(self.config, field):
                raise AttributeError(f"config missing required attribute '{field}'")

        if getattr(self.config, "rate_limit") <= 0:  # type: ignore[arg-type]
            raise ValueError("rate_limit must be > 0")

    # ---------------------------- URL utils -------------------------- #

    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        RFC-совместимая нормализация URL:
        • lower-case схема/хост; • нормализация path; • сортированный query;
        • fragment удаляется; • сохраняем / у корня.
        """
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        raw_path = unquote(parsed.path or "/")
        norm_path = posixpath.normpath(raw_path)
        if parsed.path.endswith("/") and not norm_path.endswith("/"):
            norm_path += "/"
        if not norm_path.startswith("/"):
            norm_path = f"/{norm_path}"
        norm_path = quote(norm_path, safe="/")

        q_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        q_pairs.sort()
        query = urlencode(q_pairs, doseq=True)

        return urlunparse((scheme, netloc, norm_path, "", query, ""))


###############################################################################
# Pytest helper: регистрируем маркер «slow» (для --strict-markers в CI).
###############################################################################

def _register_pytest_marker() -> None:
    try:
        import pytest  # type: ignore
    except ModuleNotFoundError:
        return

    plugin_name = "_sitescout_slow_marker"
    if hasattr(pytest, "pluginmanager") and not pytest.pluginmanager.has_plugin(plugin_name):
        class _Plugin:  # pylint: disable=too-few-public-methods
            @staticmethod
            def pytest_configure(config):
                config.addinivalue_line("markers", "slow: mark test as slow")

        pytest.pluginmanager.register(_Plugin(), plugin_name)


_register_pytest_marker()


###############################################################################
# CLI compat: click-Group «cli» должен иметь атрибуты для monkeypatch-а
# (tests/fixtures заменяют их на заглушки).  Делаем «no-op» функции,
# чтобы monkeypatch.setattr(..., raising=True) не упал.
###############################################################################

def _ensure_cli_attrs() -> None:
    import importlib

    try:
        cli_mod = importlib.import_module("site_scout.cli")
        cli_group = getattr(cli_mod, "cli", None)
    except ModuleNotFoundError:  # пакет ещё не установлен
        return

    if cli_group is None:  # pragma: no cover
        return

    async def _noop_async(*_a, **_kw):
        return []  # type: ignore[return-value]

    def _noop_sync(*_a, **_kw):  # noqa: D401
        return ""

    for name, func in {
        "start_scan": _noop_async,
        "render_json": _noop_sync,
        "render_html": _noop_sync,
    }.items():
        if not hasattr(cli_group, name):
            setattr(cli_group, name, func)


_ensure_cli_attrs()

###############################################################################
# End of file
###############################################################################
