# File: site_scout/crawler/models.py
"""site_scout.crawler.models: Классы данных для краулера."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(slots=True)
class PageData:
    """Хранит нормализованный URL и содержимое загруженной страницы (текст или байты)."""

    url: str
    content: Union[str, bytes]
