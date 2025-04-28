# site_scout/aggregator.py
"""Result aggregator that produces ScanReport instances."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, TypedDict, Union


# --------------------------------------------------------------------------- #
# Typed dictionaries for normalized items
# --------------------------------------------------------------------------- #
class PageInfo(TypedDict, total=False):
    url: str
    links: List[str]
    meta: Dict[str, Any]
    headings: Dict[str, Any]
    headers: Dict[str, Any]


class DocumentInfo(TypedDict, total=False):
    name: str
    url: str
    size: int
    mime: str


class HiddenResourceInfo(TypedDict, total=False):
    url: str
    status: Union[int, None]
    type: str
    size: int


# --------------------------------------------------------------------------- #
# ScanReport dataclass
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ScanReport:
    pages: List[PageInfo] = field(default_factory=list)
    documents: List[DocumentInfo] = field(default_factory=list)
    hidden_resources: List[HiddenResourceInfo] = field(default_factory=list)
    locales: Dict[str, List[str]] = field(default_factory=dict)

    # raw_results kept for debugging but excluded from serializers
    raw_results: Union[List[Any], None] = None

    def json(self, *, pretty: bool = False) -> str:
        """Return JSON representation excluding raw_results."""
        output = {k: v for k, v in asdict(self).items() if k != "raw_results"}
        return json.dumps(
            output,
            ensure_ascii=False,
            indent=2 if pretty else None,
        )

    def generate_html(self) -> str:
        """Very simple HTML export used by CLI/tests."""
        return f"<html><body><pre>{self.json(pretty=True)}</pre></body></html>"


# --------------------------------------------------------------------------- #
# Aggregation logic
# --------------------------------------------------------------------------- #
def aggregate_results(raw_results: List[Any]) -> ScanReport:
    """Convert raw crawl entries into a ScanReport."""
    report = ScanReport(raw_results=raw_results)

    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for entry in raw_results:
        # 1) page info
        url = _get(entry, "url", "")
        parsed = _get(entry, "parsed", None)
        report.pages.append(
            {
                "url": url,
                "links": _get(parsed, "links", []) if parsed is not None else [],
                "meta": _get(parsed, "meta", {}) if parsed is not None else {},
                "headings": _get(parsed, "headings", {}) if parsed is not None else {},
                "headers": _get(parsed, "headers", {}) if parsed is not None else {},
            }
        )

        # 2) documents
        for doc in _get(entry, "documents", []):
            report.documents.append(
                {
                    "name": _get(doc, "name", ""),
                    "url": _get(doc, "url", ""),
                    "size": _get(doc, "size", 0),
                    "mime": _get(doc, "mime", ""),
                }
            )

        # 3) hidden resources
        for hr in _get(entry, "hidden_paths", []):
            report.hidden_resources.append(
                {
                    "url": _get(hr, "url", ""),
                    "status": _get(hr, "status", None),
                    "type": _get(hr, "content_type", ""),
                    "size": _get(hr, "size", 0),
                }
            )

    # 4) locales (expected in last entry)
    if raw_results:
        last = raw_results[-1]
        locales_raw = _get(last, "locales", {})
        if isinstance(locales_raw, dict):
            report.locales = {
                lang: sorted(urls) for lang, urls in locales_raw.items() if isinstance(urls, list)
            }

    return report
