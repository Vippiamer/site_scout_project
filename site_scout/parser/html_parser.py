# === FILE: site_scout_project/site_scout/parser/html_parser.py ===
"""HTML parsing utilities for SiteScout.

The project previously imported :pyfunc:`site_scout.parser.html_parser.parse_html`
but the module was missing.  This implementation provides a minimal yet useful
`parse_html()` helper and a simple :class:`ParsedPage` dataclass so that the
Engine and other modules can rely on a stable API while we iterate.

The goal is **not** to be a full-blown scraping library but to expose enough
information for tests and higher-level logic:

* title — document <title> text or ``""`` if absent.
* links — list of absolute URLs found in <a href="…"> tags.
* text  — main visible text (usable for quick keyword checks).

If you need more structured data later, extend :class:`ParsedPage`; the
canonical public interface is the dataclass itself, so adding new optional
fields is backward-compatible.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

__all__: Sequence[str] = ("ParsedPage", "parse_html")


@dataclass(slots=True)
class ParsedPage:
    """Lightweight representation of an HTML page."""

    url: str
    title: str
    links: list[str]
    text: str

    # Convenience helpers ---------------------------------------------------
    def same_host_links(self) -> list[str]:
        """Return only links that point to the same host as *self.url*."""
        host = urlparse(self.url).netloc
        return [u for u in self.links if urlparse(u).netloc == host]


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def _normalize_url(url: str) -> str:
    """Very small URL canonicalisation (lower-case host, remove query/fragments)."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path.rstrip("/"), "", "", ""))


def parse_html(page: Any) -> ParsedPage:
    """Parse raw HTML (string) or :class:`~site_scout.crawler.crawler.PageData`.

    Parameters
    ----------
    page
        Either a *str* (HTML markup) **or** a ``PageData`` object with
        ``url`` and ``content`` attributes.  Accepting both keeps the public
        API flexible while we refactor internals.
    """
    if hasattr(page, "content") and hasattr(page, "url"):
        html = page.content
        base_url = str(page.url)
    else:
        html = str(page)
        base_url = ""

    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract links (absolute, deduplicated, stable ordering)
    seen: set[str] = set()
    links: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()  # type: ignore[index,union-attr]
        if href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        abs_url = _normalize_url(urljoin(base_url, href))
        if abs_url not in seen:
            seen.add(abs_url)
            links.append(abs_url)

    # Visible text (skip <script>, <style>, etc.)
    for element in soup(["script", "style", "noscript", "template"]):
        element.decompose()
    text = " ".join(t.strip() for t in soup.stripped_strings)

    return ParsedPage(url=base_url, title=title, links=links, text=text)
