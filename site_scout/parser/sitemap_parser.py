# --------------------------------------------------------
# site_scout/parser/sitemap_parser.py
"""Модуль: sitemap_parser.py

Парсинг sitemap.xml и извлечение всех URL.
Поддерживает базовый формат <urlset> и <sitemapindex>.
"""

from lxml import etree


def parse_sitemap(xml_content: str) -> list[str]:
    """Разбирает XML-контент sitemap и возвращает список URL.

    :param xml_content: строка с содержимым sitemap.xml
    :return: список URL из тегов <loc>

    Пример:
    ```python
    from site_scout.parser.sitemap_parser import parse_sitemap

    with open('sitemap.xml', encoding='utf-8') as f:
        content = f.read()
    urls = parse_sitemap(content)
    print(urls)
    ```
    """
    parser = etree.XMLParser(ns_clean=True, recover=True)
    root = etree.fromstring(xml_content.encode("utf-8"), parser=parser)
    # Ищем все <loc> в <url> и <sitemap>
    locs = root.findall(".//{*}loc")
    return [loc.text.strip() for loc in locs if loc.text]
