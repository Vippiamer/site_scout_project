"""
Асинхронный веб-кроулер для SiteScout.

Основные задачи:
- Отправка HTTP-запросов через aiohttp с учётом таймаутов и заголовков.
- Обход страниц по найденным ссылкам до заданной глубины.
- Соблюдение robots.txt.
- Сохранение PageData (URL, content, headers).

Использует:
- ScannerConfig из site_scout/config.py
- init_logging из site_scout/logger.py
- normalize_url и is_valid_url из site_scout/utils.py
"""
import asyncio
from typing import Dict, List, Set, Tuple
import aiohttp
from aiohttp import ClientSession
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

from site_scout.config import ScannerConfig
from site_scout.logger import init_logging
from site_scout.utils import normalize_url, is_valid_url, PageData, extract_domain


class AsyncCrawler:
    """
    Асинхронный веб-краулер с учётом robots.txt и глубины.
    """
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.logger = init_logging()
        self.semaphore = asyncio.Semaphore(config.rate_limit)
        self.visited: Set[str] = set()
        # очередь URL для обхода (URL, глубина)
        self.to_visit: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()
        # robots.txt: мапа домена -> список disallow путей
        self.robots_disallow: Dict[str, List[str]] = {}
        # Инициализация aiohttp-сессии с таймаутом
        self.session: ClientSession = ClientSession(
            headers={"User-Agent": config.user_agent},
            timeout=aiohttp.ClientTimeout(total=config.timeout)
        )

    async def close(self):
        """Закрывает aiohttp-сессию."""
        await self.session.close()

    def parse_robots(self, text: str, domain: str):
        """
        Парсит текст robots.txt и сохраняет disallow пути для данного домена.
        """
        lines = text.splitlines()
        disallows: List[str] = []
        record = False
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, _, value = line.partition(':')
            key = key.strip().lower()
            val = value.strip()
            if key == 'user-agent':
                record = (val == self.config.user_agent or val == '*')
            elif record and key == 'disallow':
                disallows.append(val)
            elif key == 'user-agent':
                record = False
        self.robots_disallow[domain] = disallows

    async def load_robots(self, base_url: str):
        """
        Загружает robots.txt и парсит disallow правила.
        """
        domain = extract_domain(base_url)
        if domain in self.robots_disallow:
            return
        robots_url = normalize_url(str(base_url), "/robots.txt")
        try:
            async with self.session.get(robots_url) as resp:
                text = await resp.text()
            self.parse_robots(text, domain)
            self.logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            self.logger.warning(f"Не удалось загрузить robots.txt: {e}")
            # Разрешаем всё
            self.robots_disallow[domain] = []

    async def crawl(self) -> List[PageData]:
        """
        Запускает обход начиная с config.base_url.
        Соблюдает max_depth и robots.txt.
        Возвращает список PageData.
        """
        start_url = normalize_url(str(self.config.base_url), "").rstrip('/')
        await self.to_visit.put((start_url, 0))
        results: List[PageData] = []

        try:
            while not self.to_visit.empty():
                url, depth = await self.to_visit.get()
                if url in self.visited or depth > self.config.max_depth:
                    self.to_visit.task_done()
                    continue

                await self.load_robots(url)
                domain = extract_domain(url)
                path = urlparse(url).path
                # проверяем disallow правила
                if any(path.startswith(p) for p in self.robots_disallow.get(domain, [])):
                    self.logger.info(f"Запрещено robots.txt: {url}")
                    self.visited.add(url)
                    self.to_visit.task_done()
                    continue

                try:
                    # Обёртка fetch_page таймаутом
                    page_data = await asyncio.wait_for(
                        self.fetch_page(url), timeout=self.config.timeout
                    )
                    results.append(page_data)
                    self.visited.add(url)

                    for link in self.extract_links(page_data):
                        norm = normalize_url(url, link).rstrip('/')
                        link_path = urlparse(norm).path
                        if is_valid_url(norm) and extract_domain(norm) == domain \
                           and norm not in self.visited \
                           and not any(link_path.startswith(p) for p in self.robots_disallow.get(domain, [])):
                            await self.to_visit.put((norm, depth + 1))
                except asyncio.TimeoutError:
                    self.logger.warning(f"Timeout при запросе {url}")
                except Exception as e:
                    self.logger.error(f"Ошибка при краулинге {url}: {e}")
                finally:
                    self.to_visit.task_done()

            await self.to_visit.join()
        finally:
            await self.close()

        return results

    def extract_links(self, page_data: PageData) -> Set[str]:
        """
        Извлекает все href из <a> на странице.
        """
        import re
        pattern = re.compile(r'href=["\'](.*?)["\']', re.IGNORECASE)
        return set(re.findall(pattern, page_data.content))

# Пример запуска напрямую
import sys
if __name__ == "__main__":
    from site_scout.config import load_config
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml")
    crawler = AsyncCrawler(cfg)
    pages = asyncio.run(crawler.crawl())
    print(f"Собрано {len(pages)} страниц")
    for p in pages:
        print(p.url)
if __name__ == "__main__":
    import sys
    from site_scout.config import load_config

    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml")
    crawler = AsyncCrawler(cfg)
    pages = asyncio.run(crawler.crawl())
    print(f"Собрано {len(pages)} страниц")
    for p in pages:
        print(p.url)
