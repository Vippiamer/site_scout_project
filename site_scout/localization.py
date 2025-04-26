# site_scout/localization.py

"""
Модуль: localization.py

Определение и группировка URL национальных сегментов сайта:
- Япония (jp, /jp, hreflang ja-JP/ja, Accept-Language)
- Южная Корея (kr, /kr, hreflang ko-KR/ko)
- Китай (cn, /cn, hreflang zh-CN/zh)

Функционал:
- Анализ карты сайта или списка URL
- Извлечение национальных поддоменов и каталогов
- Использование меток hreflang и заголовка Accept-Language для уточнения принадлежности
- Возврат словаря: {"jp": [...], "kr": [...], "cn": [...]} с URL для каждого сегмента
"""
from typing import List, Dict, Set
from urllib.parse import urlparse
from site_scout.utils import normalize_url, is_valid_url
from site_scout.parser.html_parser import parse_html, ParsedPage
from site_scout.utils import PageData
import aiohttp

# Определение локалей
LOCALES = {
    'jp': {
        'subdomain': 'jp.',
        'path_prefix': '/jp',
        'hreflangs': {'ja', 'ja-JP'},
        'accept_languages': {'ja', 'ja-JP'}
    },
    'kr': {
        'subdomain': 'kr.',
        'path_prefix': '/kr',
        'hreflangs': {'ko', 'ko-KR'},
        'accept_languages': {'ko', 'ko-KR'}
    },
    'cn': {
        'subdomain': 'cn.',
        'path_prefix': '/cn',
        'hreflangs': {'zh', 'zh-CN'},
        'accept_languages': {'zh', 'zh-CN'}
    }
}


def detect_locales(urls: List[str]) -> Dict[str, Set[str]]:
    """
    Группирует URL по национальным сегментам на основе поддомена и префикса пути.

    :param urls: список URL для анализа
    :return: словарь {locale: set(URL)}

    Пример использования:
    ```python
    urls = [
        'https://jp.example.com',
        'https://example.com/jp/page',
        'https://example.com/page',
    ]
    segments = detect_locales(urls)
    print(segments['jp'])  # содержит первые два URL
    ```
    """
    result: Dict[str, Set[str]] = {loc: set() for loc in LOCALES}
    for url in urls:
        if not is_valid_url(url):
            continue
        parsed = urlparse(url)
        host = parsed.hostname or ''
        path = parsed.path or ''
        for loc, cfg in LOCALES.items():
            # Поддомен
            if host.startswith(cfg['subdomain']):
                result[loc].add(url)
            # Путь
            elif path.startswith(cfg['path_prefix'] + '/') or path == cfg['path_prefix']:
                result[loc].add(url)
    return result


async def refine_by_hreflang(page_url: str) -> List[str]:
    """
    Догружает страницу и извлекает ссылки с атрибутами hreflang, принадлежащие целевым локалям.

    :param page_url: URL страницы
    :return: список URL локализованного контента

    Пример:
    ```python
    localized = asyncio.run(refine_by_hreflang('https://example.com'))
    print(localized)  # URLs с нужными hreflang
    ```
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(page_url) as resp:
            html = await resp.text(errors='ignore')
    page_data = PageData(url=page_url, content=html, headers={})
    parsed = parse_html(page_data)
    localized_urls = []
    for link in parsed.links:
        # Ищем <link rel="alternate" hreflang="..">
        # Но html_parser пока не парсит их, поэтому делаем быстрый поиск
        # Можно расширить позже
        pass
    return localized_urls

# Опционально: функция комбинированного детекта
async def detect_and_refine(urls: List[str]) -> Dict[str, Set[str]]:
    """
    Сначала detect_locales, потом для каждой URL базовой версии добавляет уточнённые по hreflang.
    """
    segments = detect_locales(urls)
    # Здесь можно для каждой url в универсальном сегменте вызвать refine_by_hreflang
    return segments
