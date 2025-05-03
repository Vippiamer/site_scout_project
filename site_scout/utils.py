# File: site_scout/utils.py
"""site_scout.utils: Утилитарные функции для обработки URL, работы со словарях путей и представления страниц."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, List, Sequence, Union
from urllib.parse import urlparse, urlunparse

from site_scout.logger import logger

__all__: Sequence[str] = (
    "PageData",
    "normalize_url",
    "is_valid_url",
    "extract_domain",
    "read_wordlist",
    "resolve_path",
    "remove_duplicates",
)


@dataclass(slots=True)
class PageData:
    """Контейнер для представления загруженной страницы: URL и содержимое."""

    url: str
    content: str


def normalize_url(url: str) -> str:
    """Нормализует URL: убирает параметры и фрагменты, добавляет слеш для директорий."""
    parsed = urlparse(url)
    scheme, netloc, path = parsed.scheme, parsed.netloc, parsed.path

    if path and not path.endswith("/") and not Path(path).suffix:
        path += "/"

    normalized = urlunparse((scheme, netloc, path, "", "", ""))
    logger.debug("Normalized URL: %s -> %s", url, normalized)
    return normalized


def is_valid_url(url: str, base_domain: str) -> bool:
    """Проверяет, что URL принадлежит указанному домену и использует http(s)."""
    try:
        parsed = urlparse(url)
        valid = parsed.scheme in ("http", "https") and parsed.netloc == base_domain
        logger.debug("URL valid: %s -> %s", url, valid)
        return valid
    except Exception as exc:  # pragma: no cover
        logger.error("URL validation error %s: %s", url, exc)
        return False


def extract_domain(url: str) -> str:
    """Возвращает домен из URL без дополнительных проверок."""
    return urlparse(url).netloc


def read_wordlist(path: Union[str, Path]) -> List[str]:
    """Читает wordlist, возвращает непустые строки без пробелов."""
    p = Path(path)
    if not p.exists():
        logger.error("Wordlist not found: %s", p)
        raise FileNotFoundError(f"Wordlist file not found: {p}")
    words = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    logger.debug("Loaded %d entries from wordlist %s", len(words), p)
    return words


def resolve_path(path: Union[str, Path]) -> Path:
    """Раскрывает `~`, проверяет существование и возвращает Path."""
    p = Path(path).expanduser()
    if not p.exists():
        logger.error("Path not found: %s", p)
        raise FileNotFoundError(f"Path not found: {p}")
    return p


def remove_duplicates(urls: Collection[str]) -> List[str]:
    """Удаляет дубликаты из списка URL, сохраняя порядок."""
    unique = list(dict.fromkeys(urls))
    removed = len(urls) - len(unique)
    if removed:
        logger.debug("Removed %d duplicate URLs", removed)
    return unique
