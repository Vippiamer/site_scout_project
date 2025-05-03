# File: site_scout/parser/sitemap_parser.py
"""site_scout.parser.sitemap_parser: Модуль для парсинга sitemap.xml и извлечения URL."""

from __future__ import annotations

from typing import List

from lxml import etree


def parse_sitemap(xml_content: str) -> List[str]:
    """Разбирает XML content sitemap и возвращает список URL из тегов <loc>.

    Args:
        xml_content: строка с содержимым sitemap.xml.

    Returns:
        Список URL, найденных в <loc> тегах.

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
    locs = root.findall(".//{*}loc")
    return [loc.text.strip() for loc in locs if loc.text]
