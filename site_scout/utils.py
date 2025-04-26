"""
Модуль: site_scout/utils.py

Содержит вспомогательные функции:
- normalize_url
- is_valid_url
- extract_domain, extract_subdomain
- ensure_directory, resolve_path
- get_file_extension
- read_wordlist
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Union, List
from urllib.parse import urljoin, urlparse, urldefrag


@dataclass
class PageData:
    """
    Результаты загрузки страницы:
    - url: URL страницы
    - content: текстовый контент
    - headers: HTTP-заголовки ответа
    """
    url: str
    content: str
    headers: dict


def normalize_url(base: Union[str, Path], link: str) -> str:
    """
    Объединяет базовый URL и относительный путь, удаляет фрагмент.

    Пример:
        normalize_url("https://example.com/path/", "../about.html#section")
        -> "https://example.com/about.html"
    """
    base_str = str(base)
    joined = urljoin(base_str, link.strip())
    clean, _ = urldefrag(joined)
    return clean


def is_valid_url(url: Union[str, Path]) -> bool:
    """
    Проверяет, что URL имеет схему http/https и содержит домен.
    """
    try:
        parsed = urlparse(str(url))
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def extract_domain(url: Union[str, Path]) -> str:
    """
    Возвращает основной домен (последние два сегмента хоста).

    Пример:
        extract_domain("https://sub.test.example.com/page") -> "example.com"
    """
    parsed = urlparse(str(url))
    host = parsed.hostname or ""
    parts = host.split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return host


def extract_subdomain(url: Union[str, Path]) -> str:
    """
    Возвращает поддомен (все сегменты перед основным доменом).

    Пример:
        extract_subdomain("https://sub.test.example.com/page") -> "sub.test"
    """
    parsed = urlparse(str(url))
    host = parsed.hostname or ""
    parts = host.split('.')
    if len(parts) >= 3:
        return '.'.join(parts[:-2])
    return ''


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Создает директорию, если ее нет, и возвращает объект Path.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_path(path: Union[str, Path], base: Union[str, Path]) -> Path:
    """
    Преобразует относительный путь в абсолютный на основе base.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(base) / p
    return p.resolve()


def get_file_extension(path: Union[str, Path]) -> str:
    """
    Возвращает расширение файла, включая точку, в нижнем регистре.
    """
    return Path(path).suffix.lower()


def read_wordlist(path: Union[str, Path]) -> List[str]:
    """
    Читает файл со словарем (по одному элементу на строку),
    пропуская пустые строки и строки, начинающиеся с '#'.
    """
    words: List[str] = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            part = line.strip()
            if not part or part.startswith('#'):
                continue
            words.append(part)
    return words
