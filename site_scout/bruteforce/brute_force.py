# === FILE: site_scout_project/site_scout/bruteforce/brute_force.py ===
"""Модуль для брутфорса скрытых директорий на сайте."""

import asyncio
import logging
from pathlib import Path
from typing import List

import aiohttp

from site_scout.utils import normalize_url, read_wordlist

logger = logging.getLogger(__name__)


class HiddenResource:
    """Результат поиска скрытого ресурса."""

    def __init__(self, url: str, status: int) -> None:
        self.url: str = url
        self.status: int = status

    def __repr__(self) -> str:
        return f"<HiddenResource url={self.url} status={self.status}>"


class BruteForcer:
    """Класс для поиска скрытых директорий на сайте."""

    def __init__(self, base_url: str, wordlist: List[str], concurrency: int = 10) -> None:
        self.base_url: str = base_url
        self.wordlist: List[str] = wordlist
        self.semaphore = asyncio.Semaphore(concurrency)

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> HiddenResource | None:
        """Отправка запроса и проверка статуса."""
        async with self.semaphore:
            try:
                async with session.get(url) as response:
                    if 200 <= response.status < 300:
                        return HiddenResource(url, response.status)
            except Exception as e:
                logger.exception(f"Ошибка при запросе {url}: {e}")
        return None

    async def run(self, session: aiohttp.ClientSession) -> List[HiddenResource]:
        """Запуск перебора слов."""
        tasks = []
        for word in self.wordlist:
            target_url = normalize_url(f"{self.base_url}/{word}")
            tasks.append(asyncio.create_task(self.fetch(session, target_url)))
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


async def brute_force_hidden_dirs(
    session: aiohttp.ClientSession, base_url: str, wordlist_path: Path
) -> List[HiddenResource]:
    """Функция для запуска перебора скрытых директорий."""
    wordlist = read_wordlist(wordlist_path)
    forcer = BruteForcer(base_url, wordlist)
    return await forcer.run(session)
