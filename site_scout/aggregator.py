# File: site_scout/aggregator.py
"""site_scout.aggregator: Модуль агрегатора отчетов сканирования."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, TypedDict, Union


class PageInfo(TypedDict, total=False):
    """Информация о веб-странице."""

    url: str
    links: List[str]
    meta: Dict[str, Any]
    headings: Dict[str, Any]
    headers: Dict[str, Any]


class DocumentInfo(TypedDict, total=False):
    """Информация об извлечённом документе."""

    name: str
    url: str
    size: int
    mime: str


class HiddenResourceInfo(TypedDict, total=False):
    """Информация о скрытом ресурсе (скрытые ссылки, скрипты и т.д.)."""

    url: str
    status: Union[int, None]
    type: str
    size: int


@dataclass(slots=True)
class ScanReport:
    """Результаты сканирования сайта, включая страницы, документы и скрытые ресурсы."""

    pages: List[PageInfo] = field(default_factory=list)
    documents: List[DocumentInfo] = field(default_factory=list)
    hidden_resources: List[HiddenResourceInfo] = field(default_factory=list)
    locales: Dict[str, List[str]] = field(default_factory=dict)

    raw_results: Union[List[Any], None] = None

    def json(self, *, pretty: bool = False) -> str:
        """Возвращает JSON-представление ScanReport без сырых данных."""
        output = {k: v for k, v in asdict(self).items() if k != "raw_results"}
        return json.dumps(output, ensure_ascii=False, indent=2 if pretty else None)

    def generate_html(self) -> str:
        """Генерирует простую HTML для CLI или тестов."""
        return f"<html><body><pre>{self.json(pretty=True)}</pre></body></html>"


def _aggregate_pages(raw_results: List[Any]) -> List[PageInfo]:
    """Преобразует страницы из сырых данных."""
    pages: List[PageInfo] = []
    for entry in raw_results:
        url = entry.get("url", "") if isinstance(entry, dict) else getattr(entry, "url", "")
        parsed = (
            entry.get("parsed", None) if isinstance(entry, dict) else getattr(entry, "parsed", None)
        )
        pages.append(
            {
                "url": url,
                "links": getattr(parsed, "links", []) if parsed else [],
                "meta": getattr(parsed, "meta", {}) if parsed else {},
                "headings": getattr(parsed, "headings", {}) if parsed else {},
                "headers": getattr(parsed, "headers", {}) if parsed else {},
            }
        )
    return pages


def _aggregate_documents(raw_results: List[Any]) -> List[DocumentInfo]:
    """Преобразует документы из сырых данных."""
    docs_list: List[DocumentInfo] = []
    for entry in raw_results:
        docs = (
            entry.get("documents", [])
            if isinstance(entry, dict)
            else getattr(entry, "documents", [])
        )
        for doc in docs:
            docs_list.append(
                {
                    "name": (
                        getattr(doc, "name", "")
                        if not isinstance(doc, dict)
                        else doc.get("name", "")
                    ),
                    "url": (
                        getattr(doc, "url", "") if not isinstance(doc, dict) else doc.get("url", "")
                    ),
                    "size": (
                        getattr(doc, "size", 0) if not isinstance(doc, dict) else doc.get("size", 0)
                    ),
                    "mime": (
                        getattr(doc, "mime", "")
                        if not isinstance(doc, dict)
                        else doc.get("mime", "")
                    ),
                }
            )
    return docs_list


def _aggregate_hidden(raw_results: List[Any]) -> List[HiddenResourceInfo]:
    """Преобразует скрытые ресурсы из сырых данных."""
    hidden_list: List[HiddenResourceInfo] = []
    for entry in raw_results:
        hrs = (
            entry.get("hidden_paths", [])
            if isinstance(entry, dict)
            else getattr(entry, "hidden_paths", [])
        )
        for hr in hrs:
            hidden_list.append(
                {
                    "url": (
                        getattr(hr, "url", "") if not isinstance(hr, dict) else hr.get("url", "")
                    ),
                    "status": (
                        getattr(hr, "status", None)
                        if not isinstance(hr, dict)
                        else hr.get("status")
                    ),
                    "type": (
                        getattr(hr, "content_type", "")
                        if not isinstance(hr, dict)
                        else hr.get("content_type", "")
                    ),
                    "size": (
                        getattr(hr, "size", 0) if not isinstance(hr, dict) else hr.get("size", 0)
                    ),
                }
            )
    return hidden_list


def aggregate_results(raw_results: List[Any]) -> ScanReport:
    """Собирает все части отчёта в ScanReport."""
    report = ScanReport(raw_results=raw_results)
    report.pages = _aggregate_pages(raw_results)
    report.documents = _aggregate_documents(raw_results)
    report.hidden_resources = _aggregate_hidden(raw_results)
    # Обработка локалей
    if raw_results:
        last = raw_results[-1]
        locales_raw = (
            last.get("locales", {}) if isinstance(last, dict) else getattr(last, "locales", {})
        )
        if isinstance(locales_raw, dict):
            report.locales = {
                lang: sorted(urls) for lang, urls in locales_raw.items() if isinstance(urls, list)
            }
    return report
