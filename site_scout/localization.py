# === FILE: site_scout_project/site_scout/localization.py ===
"""Модуль для локализации ресурсов веб-сайтов."""

import re
from pathlib import Path
from typing import Collection

from site_scout.logger import logger
from site_scout.utils import PageData, is_valid_url, normalize_url


def normalize_path(path: str) -> str:
    """Удаляет параметры и фрагменты из URL."""
    return re.sub(r"[#?].*", "", path)


def extract_links_from_content(content: str) -> list[str]:
    """Извлекает все ссылки из текста страницы."""
    links = re.findall(r"href=['\"](.*?)['\"]", content, flags=re.IGNORECASE)
    return [link for link in links if link]


def localize_resources(resources: list[str], base_domain: str) -> list[str]:
    """Фильтрует и нормализует ресурсы, принадлежащие базовому домену."""
    localized = []
    for res in resources:
        normalized = normalize_url(res)
        if is_valid_url(normalized, base_domain):
            localized.append(normalized)
    return localized


def find_localized_segments(content: str, base_domain: str) -> list[str]:
    """Ищет локализованные сегменты в HTML содержимом."""
    links = extract_links_from_content(content)
    return localize_resources(links, base_domain)


def get_localized_urls(pages: Collection[PageData], base_domain: str) -> list[str]:
    """Проходит по страницам и собирает локализованные URL."""
    localized_urls = []
    for page in pages:
        localized_urls.extend(find_localized_segments(page.content, base_domain))
    return localized_urls


def extract_segments_from_urls(urls: list[str], base_domain: str) -> list[str]:
    """Извлекает сегменты путей из списка URL, принадлежащих базовому домену."""
    segments = []
    for url in urls:
        if is_valid_url(url, base_domain):
            path = normalize_path(url)
            segment = Path(path).parts[1] if len(Path(path).parts) > 1 else ""
            if segment:
                segments.append(segment)
    return segments


def remove_duplicates(urls: Collection[str]) -> list[str]:
    """Удаляет дублирующиеся URL."""
    unique_urls = list(set(urls))
    logger.debug(f"Удалено {len(urls) - len(unique_urls)} дубликатов")
    return unique_urls
