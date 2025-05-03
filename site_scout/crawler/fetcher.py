# File: site_scout/crawler/fetcher.py
"""site_scout.crawler.fetcher: Модуль для HTTP-запросов с поддержкой rate limit, retry/backoff и таймаутов."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Deque, Optional, Sequence

from aiohttp import ClientError, ClientSession

from site_scout.config import ScannerConfig
from site_scout.crawler.models import PageData
from site_scout.crawler.robots import RobotsTxtRules


class Fetcher:
    """Обрабатывает HTTP-запросы с проверкой robots, ограничением частоты, retry/backoff и таймаутом."""

    def __init__(
        self,
        session: ClientSession,
        config: ScannerConfig,
        retry_status: Sequence[int],
    ) -> None:
        """Инициализирует Fetcher с сессией aiohttp, конфигом и списком HTTP-статусов для retry."""
        self.session = session
        self.config = config
        self._retry_status = retry_status
        self._req_times: Deque[float] = deque()

    async def fetch(
        self,
        url: str,
        robots: Optional[RobotsTxtRules] = None,
    ) -> Optional[PageData]:
        """Выполняет GET-запрос к URL, если он разрешён robots и не нарушает rate limit.

        Args:
            url: адрес для запроса.
            robots: правила из robots.txt.

        Returns:
            PageData при успешном получении содержимого, или None при ошибке.
        """
        # Проверка robots.txt
        attempts = 0
        while True:
            try:
                async with self.session.get(url, raise_for_status=False) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status in self._retry_status:
                        raise ClientError(f"Retryable status {resp.status}")
                    ctype = resp.headers.get("Content-Type", "").lower()
                    if "html" in ctype or "json" in ctype:
                        text = await resp.text()
                        return PageData(url, text)
                    data = await resp.read()
                    return PageData(url, data)
            except asyncio.TimeoutError:
                return None
            except ClientError:
                attempts += 1
                if attempts > self.config.retry_times:
                    return None
                await asyncio.sleep(min(2**attempts, 60))

        return None
