# site_scout/bruteforce/brute_force.py

"""
Модуль: brute_force.py

Словарный brute-force скрытых файлов и директорий.

Основные задачи:
- Асинхронная генерация URL по словарям (директории и файлы).
- HEAD-запросы для проверки существования (200 OK, 301/302 перенаправления).
- GET-запросы для скачивания или проверки содержимого найденных файлов.
- Логирование найденных ресурсов и сбор метаданных.
"""
import asyncio
from pathlib import Path
from typing import List, Dict
import aiohttp
from aiohttp import ClientSession

from site_scout.config import ScannerConfig
from site_scout.logger import init_logging
from site_scout.utils import read_wordlist, resolve_path, extract_domain, normalize_url


class HiddenResource:
    """
    Информация о найденном скрытом ресурсе.
    """
    def __init__(self, url: str, status: int, content_type: str, size: int):
        self.url = url
        self.status = status
        self.content_type = content_type
        self.size = size

    def __repr__(self):
        return f"HiddenResource(url={self.url}, status={self.status}, type={self.content_type}, size={self.size})"


class BruteForcer:
    """
    Класс для выполнения brute-force сканирования скрытых путей.
    """
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.logger = init_logging()
        # Загрузка словарей директорий и файлов
        self.dir_list = read_wordlist(config.wordlists['paths'])
        self.file_list = read_wordlist(config.wordlists['files'])
        self.semaphore = asyncio.Semaphore(config.rate_limit)
        self.domain = extract_domain(config.base_url)
        # Создаём папку для сохранения найденных файлов
        self.download_dir = resolve_path("downloads", Path.cwd())
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def scan_paths(self, base_url: str) -> List[HiddenResource]:
        """
        Запускает сканирование директорий и файлов по словарю.

        :param base_url: базовый URL сайта
        :return: список найденных HiddenResource

        Пример:
        ```python
        from site_scout.bruteforce.brute_force import BruteForcer
        from site_scout.config import load_config
        import asyncio

        cfg = load_config('configs/default.yaml')
        bf = BruteForcer(cfg)
        resources = asyncio.run(bf.scan_paths(cfg.base_url))
        print(resources)
        ```
        """
        found: List[HiddenResource] = []
        async with aiohttp.ClientSession(headers={'User-Agent': self.config.user_agent},
                                         timeout=aiohttp.ClientTimeout(total=self.config.timeout)) as session:

            # Генерация задач для директорий и файлов
            tasks = []
            for path in self.dir_list:
                url = normalize_url(base_url, f"/{path}/")
                tasks.append(self.check_path(session, url, is_file=False))
            for filename in self.file_list:
                url = normalize_url(base_url, f"/{filename}")
                tasks.append(self.check_path(session, url, is_file=True))

            # Ограниченный параллелизм
            for i in range(0, len(tasks), self.config.rate_limit):
                batch = tasks[i:i + self.config.rate_limit]
                results = await asyncio.gather(*batch)
                for res in results:
                    if res:
                        found.append(res)

        return found

    async def check_path(self, session: ClientSession, url: str, is_file: bool) -> HiddenResource:
        """
        Проверяет доступность URL методами HEAD и GET (для файлов).

        :param session: aiohttp.ClientSession
        :param url: полный URL до проверки
        :param is_file: флаг, нужно ли скачивать содержимое
        :return: HiddenResource или None
        """
        async with self.semaphore:
            try:
                async with session.head(url, allow_redirects=True) as resp:
                    status = resp.status
                    if status == 200:
                        content_type = resp.headers.get('Content-Type', '')
                        size = int(resp.headers.get('Content-Length', 0))
                        hr = HiddenResource(url, status, content_type, size)
                        self.logger.info(f"Найден ресурс: {hr}")
                        # Для файлов делаем GET и сохраняем
                        if is_file and 'text/html' not in content_type:
                            await self.download_file(session, url)
                        return hr
            except Exception as e:
                self.logger.warning(f"Ошибка при проверке {url}: {e}")
        return None

    async def download_file(self, session: ClientSession, url: str):
        """
        Скачивает файл по URL и сохраняет в директорию downloads.

        :param session: aiohttp.ClientSession
        :param url: URL файла
        """
        filename = url.split('/')[-1]
        path = self.download_dir / filename
        try:
            async with session.get(url) as resp:
                content = await resp.read()
                path.write_bytes(content)
                self.logger.info(f"Скачан файл: {path} ({len(content)} bytes)")
        except Exception as e:
            self.logger.error(f"Не удалось скачать файл {url}: {e}")
