# === FILE: site_scout_project/site_scout/aggregator.py ===
"""Result aggregator that produces :class:`ScanReport` instances."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, TypedDict


# --------------------------------------------------------------------------- #
# Typed dictionaries for normalised items                                     #
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
    status: int | None
    type: str
    size: int


# --------------------------------------------------------------------------- #
# ScanReport dataclass                                                        #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ScanReport:
    pages: List[PageInfo] = field(default_factory=list)
    documents: List[DocumentInfo] = field(default_factory=list)
    hidden_resources: List[HiddenResourceInfo] = field(default_factory=list)
    locales: Dict[str, List[str]] = field(default_factory=dict)

    # raw results kept for debugging but excluded from serialisers
    raw_results: List[Dict[str, Any]] | None = None

    # ------------------------------------------------------------------#
    # serialisers used by CLI/tests                                     #
    # ------------------------------------------------------------------#
    def json(self, *, pretty: bool = False) -> str:
        """Return JSON representation."""
        return json.dumps(
            {k: v for k, v in asdict(self).items() if k != "raw_results"},
            ensure_ascii=False,
            indent=2 if pretty else None,
        )

    def generate_html(self) -> str:
        """Very simple HTML export used by CLI."""
        return "<html><body><pre>" + self.json(pretty=True) + "</pre></body></html>"


# --------------------------------------------------------------------------- #
# Aggregation logic                                                           #
# --------------------------------------------------------------------------- #
def aggregate_results(raw_results: List[Dict[str, Any]]) -> ScanReport:
    report = ScanReport(raw_results=raw_results)

    for entry in raw_results:
        # 1) page info --------------------------------------------------- #
        parsed = entry.get("parsed")
        report.pages.append(
            {
                "url": entry.get("url", ""),
                "links": getattr(parsed, "links", []),
                "meta": getattr(parsed, "meta", {}),
                "headings": getattr(parsed, "headings", {}),
                "headers": getattr(parsed, "headers", {}),
            }
        )

        # 2) documents --------------------------------------------------- #
        for doc in entry.get("documents", []):
            report.documents.append(
                {
                    "name": getattr(doc, "name", ""),
                    "url": getattr(doc, "url", ""),
                    "size": getattr(doc, "size", 0),
                    "mime": getattr(doc, "mime", ""),
                }
            )

        # 3) hidden resources ------------------------------------------- #
        for hr in entry.get("hidden_paths", []):
            report.hidden_resources.append(
                {
                    "url": getattr(hr, "url", ""),
                    "status": getattr(hr, "status", None),
                    "type": getattr(hr, "content_type", ""),
                    "size": getattr(hr, "size", 0),
                }
            )

    # 4) locales (expected on last record) ------------------------------ #
    if raw_results and "locales" in raw_results[-1]:
        locs: Dict[str, set[str]] = raw_results[-1].get("locales", {})
        report.locales = {lang: sorted(urls) for lang, urls in locs.items()}

    return report
