# site_scout/doc_finder.py

"""
Модуль: doc_finder.py

Поиск и проверка ссылок на документы (.pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx).

Основные задачи:
- Получение ParsedPage с ссылками.
- Фильтрация ссылок по расширениям.
- Асинхронная проверка доступности (HEAD-запросы).
- Сбор метаданных: URL, имя файла, размер (Content-Length), MIME-тип.
"""
import asyncio
from typing import List
import aiohttp
from urllib.parse import urlparse, unquote, urljoin

from site_scout.utils import is_valid_url
from site_scout.logger import init_logging

# Список целевых расширений (в нижнем регистре)
TARGET_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}


class DocumentInfo:
    """
    Данные по найденному документу.
    """
    def __init__(self, url: str, name: str, size: int, mime: str):
        self.url = url
        self.name = name
        self.size = size
        self.mime = mime

    def __repr__(self):
        return f"DocumentInfo(name={self.name}, size={self.size}, mime={self.mime}, url={self.url})"


async def find_documents(parsed_page: 'ParsedPage') -> List[DocumentInfo]:
    """
    Ищет ссылки на документы в parsed_page.links.

    1) Фильтрация по расширениям.
    2) Проверка URL (валидность).
    3) Асинхронные HEAD-запросы для получения метаданных.

    :param parsed_page: объект ParsedPage (html_parser)
    :return: список DocumentInfo

    Пример:
    ```python
    from site_scout.parser.html_parser import parse_html
    from site_scout.doc_finder import find_documents
    import asyncio

    # parsed = parse_html(page_data)
    docs = asyncio.run(find_documents(parsed))
    print(docs)
    ```
    """
    logger = init_logging()
    docs: List[DocumentInfo] = []
    # Отбор ссылок с нужным расширением
    candidates = []
    for link in parsed_page.links:
        # Приводим к абсолютному (если нужно)
        abs_url = urljoin(parsed_page.url, link)
        if not is_valid_url(abs_url):
            continue
        path = urlparse(abs_url).path
        ext = ''
        if '.' in path:
            ext = path[path.rfind('.'):].lower()
        if ext in TARGET_EXTENSIONS:
            candidates.append(abs_url)

    async def fetch_head(session: aiohttp.ClientSession, url: str):
        try:
            async with session.head(url, allow_redirects=True) as resp:
                headers = resp.headers
                size = int(headers.get('Content-Length', 0))
                mime = headers.get('Content-Type', '')
                name = unquote(urlparse(url).path.split('/')[-1])
                docs.append(DocumentInfo(url=url, name=name, size=size, mime=mime))
        except Exception as e:
            logger.warning(f"Не удалось получить HEAD для {url}: {e}")

    # Параллельные HEAD-запросы с семафором
    timeout = aiohttp.ClientTimeout(total=parsed_page.headers.get('timeout', 10))
    async with aiohttp.ClientSession(timeout=timeout, headers={'User-Agent': 'SiteScoutBot/1.0'}) as session:
        tasks = [fetch_head(session, url) for url in candidates]
        await asyncio.gather(*tasks)

    return docs
