"""Модуль для перебора скрытых директорий на сайте."""

import asyncio
import logging
from pathlib import Path
from typing import List, Union

import aiohttp

from site_scout.utils import normalize_url, read_wordlist

logger = logging.getLogger(__name__)


class HiddenResource:
    """Результат поиска скрытого ресурса."""

    def __init__(self, url: str, status: int) -> None:
        """Инициализирует скрытый ресурс с URL и HTTP-статусом."""
        self.url: str = url
        self.status: int = status

    def __repr__(self) -> str:
        """Строковое представление объекта HiddenResource для отладки."""
        return f"<HiddenResource url={self.url} status={self.status}>"


class BruteForcer:
    """Класс для поиска скрытых директорий на сайте."""

    def __init__(self, base_url: str, wordlist: List[str], concurrency: int = 10) -> None:
        """Инициализирует BruteForcer с базовым URL, списком слов и уровнем конкуренции."""
        self.base_url: str = base_url
        self.wordlist: List[str] = wordlist
        self.semaphore = asyncio.Semaphore(concurrency)

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> Union[HiddenResource, None]:
        """Отправляет запрос к URL и возвращает HiddenResource при статусе 2xx."""
        async with self.semaphore:
            try:
                async with session.get(url) as response:
                    if 200 <= response.status < 300:
                        return HiddenResource(url, response.status)
            except Exception as e:
                logger.exception(f"Ошибка при запросе {url}: {e}")
        return None

    async def run(self, session: aiohttp.ClientSession) -> List[HiddenResource]:
        """Запускает перебор слов и собирает найденные скрытые ресурсы."""
        tasks = []
        for word in self.wordlist:
            target_url = normalize_url(f"{self.base_url}/{word}")
            tasks.append(asyncio.create_task(self.fetch(session, target_url)))
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


async def brute_force_hidden_dirs(
    session: aiohttp.ClientSession, base_url: str, wordlist_path: Path
) -> List[HiddenResource]:
    """Запускает перебор скрытых директорий по файлу словаря и возвращает найденные ресурсы."""
    wordlist = read_wordlist(wordlist_path)
    forcer = BruteForcer(base_url, wordlist)
    return await forcer.run(session)
