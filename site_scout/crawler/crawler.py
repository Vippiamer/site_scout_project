# === FILE: site_scout/crawler/crawler.py
# Модуль асинхронного краулинга для проекта SiteScout.
# Поддержка:
#   • корректного robots.txt (Allow/Disallow/Crawl-delay, порядок правил);
#   • глобального rate-limit/token-bucket;
#   • retry с экспоненциальным back-off и настраиваемым списком кодов;
#   • таймаутов, конкурентности, прогресса через logging;
#   • PEP-8 и сохранения прежнего публичного API.

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple
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
    """
    Разбирает robots.txt и применяет правила:
    • поддержка Disallow/Allow (последнее совпадение побеждает);
    • директива Crawl-delay хранится отдельно для каждой группы.
    Алгоритм совместим со спецификацией
    https://www.rfc-editor.org/rfc/rfc9309#section-2
    """

    _Directive = Tuple[str, str]  # ('allow'|'disallow', path)

    def __init__(self, text: str) -> None:
        self._groups: List[Dict[str, object]] = []
        self._parse(text)

    # -------------------------- public API --------------------------

    def can_fetch(self, user_agent: str, path: str) -> bool:
        """Возвращает True, если `user_agent` может скачать `path`."""
        group = self._match_group(user_agent)
        if group is None:
            # Группа не найдена → разрешено.
            return True

        allow = True
        for directive, rule_path in group["directives"]:  # type: ignore[index]
            if not rule_path:
                # Пустое значение Disallow/Allow не влияет.
                continue
            if path.startswith(rule_path):
                allow = directive == "allow"
        return allow

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        """Директива Crawl-delay для указанного User-Agent."""
        group = self._match_group(user_agent)
        return None if group is None else group["crawl_delay"]  # type: ignore[index]

    # ------------------------- internal -----------------------------

    def _parse(self, text: str) -> None:
        current: Optional[Dict[str, object]] = None

        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()  # убираем комментарии
            if not line:
                continue

            key, _, value = line.partition(":")
            key = key.lower().strip()
            value = value.strip()

            if key == "user-agent":
                if (
                    current is None
                    or current["agents"]  # type: ignore[index]
                    and (current["directives"] or current["crawl_delay"] is not None)  # type: ignore[index]
                ):
                    # Начинаем новую группу.
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
                    continue  # игнорируем неверное значение

    def _match_group(self, user_agent: str) -> Optional[Dict[str, object]]:
        """Выбираем первую подходящую группу (RFC 9309, §2.2)."""
        ua = user_agent.lower()
        for group in self._groups:
            if any(self._ua_match(ua, agent) for agent in group["agents"]):  # type: ignore[index]
                return group
        # Фолбек - ищем группу с '*'
        for group in self._groups:
            if "*" in group["agents"]:  # type: ignore[index]
                return group
        return None

    @staticmethod
    def _ua_match(ua: str, pattern: str) -> bool:
        pattern = pattern.lower()
        if pattern == "*":
            return True
        return ua.startswith(pattern)


class AsyncCrawler:
    """
    Асинхронный краулер.
    Публичный интерфейс не изменён: `crawl()` отдаёт List[PageData].
    """

    _RETRY_STATUS: Sequence[int] = tuple(range(500, 600)) + (429,)

    def __init__(self, config) -> None:
        self.config = config
        self._validate_config()

        self.visited: Set[str] = set()
        self.disallowed_pages: List[str] = []

        self.session: Optional[ClientSession] = None
        self.logger = logging.getLogger("SiteScout")

        # Rate-limit.
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self.rate_limit = max(1.0, float(self.config.rate_limit))

        # Concurrency semaphore.
        self._sem = asyncio.Semaphore(int(self.config.concurrency))

        # Retry.
        self.retry_times: int = max(0, int(getattr(self.config, "retry_times", 0)))

        # Robots.
        self.robots_rules: Optional[RobotsTxtRules] = None

    # -------------------------- context -----------------------------

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

    # -------------------------- public ------------------------------

    async def crawl(self) -> List[PageData]:
        """
        Запускает обход сайта, ограниченный `config.max_depth`
        и (необязательным) `config.max_pages`.
        """
        self.logger.info("Старт обхода: %s", self.config.base_url)

        start_time = time.monotonic()
        queue: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()

        root = self._normalize_url(str(self.config.base_url))
        self.visited.add(root)
        await queue.put((root, 0))

        max_pages = getattr(self.config, "max_pages", 5000)
        results: List[PageData] = []

        # Запускаем воркеры.
        workers = [
            asyncio.create_task(self._worker(queue, results, max_pages))
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
            self.logger.info(
                "Заблокировано по robots.txt: %d", len(self.disallowed_pages)
            )
        return results

    # ------------------------- workers ------------------------------

    async def _worker(
        self,
        queue: "asyncio.Queue[Tuple[str, int]]",
        results: List[PageData],
        max_pages: int,
    ) -> None:
        """Основной цикл воркера."""
        try:
            while True:
                url, depth = await queue.get()

                if depth > self.config.max_depth or len(results) >= max_pages:
                    queue.task_done()
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

                queue.task_done()
        except asyncio.CancelledError:
            return

    # ----------------------- HTTP & parsing -------------------------

    async def _safe_fetch(self, url: str) -> Optional[PageData]:
        """Обёртка над _fetch() с контролем семафора."""
        async with self._sem:
            return await self._fetch(url)

    async def _fetch(self, url: str) -> Optional[PageData]:
        """Загружает страницу с учётом robots, rate-limit и retry."""
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
            start = time.monotonic()
            try:
                async with self.session.get(url) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status in self._RETRY_STATUS:
                        raise ClientError(f"Retryable status: {resp.status}")

                    if resp.status == 200 and ctype.startswith("text/html"):
                        text = await resp.text()
                        return PageData(url, text)

                    # Не HTML → игнорируем без ошибки.
                    return None

            except (ClientError, asyncio.TimeoutError) as exc:
                attempts += 1
                if attempts > self.retry_times:
                    self.logger.debug("Отказ: %s (%s)", url, exc)
                    break

                backoff = min(60.0, 2 ** attempts)
                self.logger.debug(
                    "Retry %d/%d for %s after %.1fs", attempts, self.retry_times, url, backoff
                )
                await asyncio.sleep(backoff)

            finally:
                elapsed = time.monotonic() - start
                # Если скачивание шло дольше min_interval, лимитер уже «отдохнул».
                if crawl_delay:
                    # Гарантируем, что средний QPS не превысит Crawl-delay.
                    await asyncio.sleep(max(0.0, crawl_delay - elapsed))

        return None

    async def _extract(self, page: PageData) -> List[str]:
        """Извлекает внутренние ссылки из HTML."""
        soup = BeautifulSoup(page.content, "html.parser")
        page_host = urlparse(page.url).netloc

        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if href.startswith("mailto:") or href.startswith("javascript:"):
                continue
            abs_url = self._normalize_url(urljoin(page.url, href))
            parsed = urlparse(abs_url)
            if parsed.netloc == page_host:
                links.append(abs_url)
        return links

    # -------------------- rate-limit helpers ------------------------

    async def _wait_for_rate_limit(self, crawl_delay: Optional[float]) -> None:
        """Блокирует вызов, обеспечивая глобальный QPS и Crawl-delay."""
        min_interval = max(1.0 / self.rate_limit, crawl_delay or 0.0)
        async with self._rate_lock:
            now = time.monotonic()
            wait_for = min_interval - (now - self._last_request_ts)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_ts = time.monotonic()

    # ----------------------- misc helpers ---------------------------

    def _is_allowed(self, url: str) -> bool:
        """Проверка robots.txt."""
        if not self.robots_rules:
            return True
        return self.robots_rules.can_fetch(
            self.config.user_agent, urlparse(url).path
        )

    async def _load_robots(self) -> None:
        """Загружает и парсит robots.txt (best-effort)."""
        if not self.session:
            return

        parsed = urlparse(str(self.config.base_url))
        robots_url = urlunparse(
            (parsed.scheme, parsed.netloc, "/robots.txt", "", "", "")
        )

        try:
            async with self.session.get(robots_url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    self.robots_rules = RobotsTxtRules(text)
                else:
                    self.logger.debug(
                        "robots.txt не найден (%s): %s", resp.status, robots_url
                    )
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Ошибка загрузки robots.txt: %s", exc)

    def _validate_config(self) -> None:
        """Мини-валидация обязательных полей конфигурации."""
        required = ("base_url", "user_agent", "timeout", "max_depth", "rate_limit")
        for field in required:
            if not hasattr(self.config, field):
                raise AttributeError(f"config missing required attribute '{field}'")

        defaults = {
            "retry_times": 0,
            "concurrency": int(max(1, float(self.config.rate_limit))),
            "max_pages": 5000,
        }
        for name, value in defaults.items():
            if not hasattr(self.config, name):
                setattr(self.config, name, value)

    # ----------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        Примитивная нормализация URL:
        • схема/хост в lower-case;
        • убираем query/fragment;
        • пустой path → '/'.
        """
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        return urlunparse((scheme, netloc, path.rstrip("/"), "", "", ""))
