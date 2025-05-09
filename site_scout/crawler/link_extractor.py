# File: site_scout/crawler/link_extractor.py
"""site_scout.crawler.link_extractor: Утилиты для извлечения ссылок и нормализации URL."""

from __future__ import annotations

from typing import List
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from site_scout.crawler.models import PageData


def extract_links(page: PageData) -> List[str]:
    """Извлекает внутренние HTTP(S)-ссылки из содержимого страницы."""
    soup = BeautifulSoup(page.content, "html.parser")
    base_netloc = urlparse(page.url).netloc
    links: List[str] = []
    for tag in soup.find_all("a", href=True):
        if not isinstance(tag, Tag):
            continue
        href_val = tag.get("href")
        if not isinstance(href_val, str):
            continue
        raw = href_val.strip()
        if raw.startswith(("mailto:", "javascript:")):
            continue
        absolute = urljoin(page.url, raw)
        parsed = urlparse(absolute)
        if parsed.scheme in ("http", "https") and parsed.netloc == base_netloc:
            links.append(absolute)
    return links


def normalize_url(url: str) -> str:
    """Приводит URL к стандартному виду: нижний регистр схемы и хоста, удаление слешей."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    if path == "/":
        return f"{scheme}://{netloc}"
    return urlunparse((scheme, netloc, path, "", "", ""))
