# === FILE: site_scout_project/site_scout/utils.py ===
"""
Утилитарные функции для обработки URL, работы со словарями путей и представления
страниц, используемые во всём проекте **SiteScout**.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, List, Sequence
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


# --------------------------------------------------------------------------- #
# Типы данных                                                                  #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class PageData:
    """Мини‑контейнер для представления загруженной страницы."""

    url: str
    content: str


# --------------------------------------------------------------------------- #
# URL helpers                                                                  #
# --------------------------------------------------------------------------- #


def normalize_url(url: str) -> str:
    """Нормализует URL.

    * удаляет ``params``, ``query`` и ``fragment``;
    * добавляет завершающий слэш для директорий без расширения.
    """
    parsed = urlparse(url)
    scheme, netloc, path = parsed.scheme, parsed.netloc, parsed.path

    # Добавляем слэш в конце пути, если это директория (нет расширения)
    if path and not path.endswith("/") and not Path(path).suffix:
        path += "/"

    normalized = urlunparse((scheme, netloc, path, "", "", ""))
    logger.debug("Normalized URL: %s -> %s", url, normalized)
    return normalized


def is_valid_url(url: str, base_domain: str) -> bool:
    """Проверяет, что URL принадлежит базовому домену и использует HTTP(S)."""
    try:
        parsed = urlparse(url)
        valid = parsed.scheme in ("http", "https") and parsed.netloc == base_domain
        logger.debug("URL valid: %s -> %s", url, valid)
        return valid
    except Exception as exc:  # pragma: no cover — логируем, но не падаем на тестах
        logger.error("URL validation error for %s: %s", url, exc)
        return False


def extract_domain(url: str) -> str:
    """Извлекает домен из URL без дополнительных проверок."""
    return urlparse(url).netloc


# --------------------------------------------------------------------------- #
# File helpers                                                                 #
# --------------------------------------------------------------------------- #


def read_wordlist(path: Path) -> List[str]:
    """Читает wordlist построчно и возвращает непустые строки без пробелов."""
    if not path.exists():
        logger.error("Wordlist not found: %s", path)
        raise FileNotFoundError(f"Wordlist file not found: {path}")

    words = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    logger.debug("Loaded %d entries from wordlist %s", len(words), path)
    return words


def resolve_path(path: str | Path) -> Path:
    """Раскрывает `~`, возвращает :class:`Path` и проверяет существование."""
    p = Path(path).expanduser()
    if not p.exists():
        logger.error("Path not found: %s", p)
        raise FileNotFoundError(f"Path not found: {p}")
    return p


# --------------------------------------------------------------------------- #
# Misc helpers                                                                 #
# --------------------------------------------------------------------------- #


def remove_duplicates(urls: Collection[str]) -> List[str]:
    """Сохраняя порядок, удаляет дублирующиеся URL из коллекции."""
    unique: List[str] = list(dict.fromkeys(urls))
    removed = len(urls) - len(unique)
    if removed:
        logger.debug("Removed %d duplicate URLs", removed)
    return unique
