# site_scout/parser/html_parser.py
"""
Модуль: html_parser.py

Парсинг HTML-страницы.
- Извлечение всех ссылок (<a href>)
- Сбор meta-тегов (name, http-equiv, charset)
- Извлечение заголовков <h1>-<h6>
- Сбор HTTP-заголовков из PageData
"""
from dataclasses import dataclass, field
from typing import List, Dict
from bs4 import BeautifulSoup
from site_scout.utils import PageData

@dataclass
class ParsedPage:
    url: str
    links: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    headings: Dict[str, List[str]] = field(default_factory=lambda: {f'h{i}': [] for i in range(1,7)})
    headers: Dict[str, str] = field(default_factory=dict)


def parse_html(page_data: PageData) -> ParsedPage:
    """
    Разбирает HTML-контент страницы и возвращает ParsedPage.

    :param page_data: объект PageData с полями url, content, headers
    :return: ParsedPage с ссылками, meta, заголовками и HTTP-заголовками

    Пример использования:
    ```python
    from site_scout.parser.html_parser import parse_html
    from site_scout.utils import PageData

    page = PageData(
        url="https://example.com",
        content="<html>...</html>",
        headers={"Content-Type": "text/html"}
    )
    parsed = parse_html(page)
    print(parsed.links)
    print(parsed.meta)
    print(parsed.headings['h1'])
    print(parsed.headers)
    ```
    """
    soup = BeautifulSoup(page_data.content, 'lxml')
    parsed = ParsedPage(url=page_data.url)
    # Извлечение ссылок
    for tag in soup.find_all('a', href=True):
        parsed.links.append(tag['href'].strip())
    # Сбор meta-тегов
    for tag in soup.find_all('meta'):
        if 'name' in tag.attrs and 'content' in tag.attrs:
            parsed.meta[tag.attrs['name']] = tag.attrs['content']
        elif 'http-equiv' in tag.attrs and 'content' in tag.attrs:
            parsed.meta[tag.attrs['http-equiv']] = tag.attrs['content']
        elif 'charset' in tag.attrs:
            parsed.meta['charset'] = tag.attrs['charset']
    # Извлечение заголовков h1-h6
    for i in range(1, 7):
        tag_name = f'h{i}'
        for hdr in soup.find_all(tag_name):
            text = hdr.get_text(strip=True)
            if text:
                parsed.headings[tag_name].append(text)
    # HTTP-заголовки
    parsed.headers = page_data.headers
    return parsed

