# site_scout/crawler/models.py
"""
Data models for the SiteScout crawler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(slots=True)
class PageData:
    """Holds normalized URL and content of a fetched page (text or binary)."""

    url: str
    content: Union[str, bytes]
