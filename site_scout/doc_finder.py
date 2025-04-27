# === FILE: site_scout_project/site_scout/doc_finder.py ===

"""Module for finding documents on website pages.

Defines classes and methods for extracting document links.
"""

from dataclasses import dataclass


@dataclass
class ParsedPage:
    """Parsed page results."""

    url: str
    links: list[str]


@dataclass
class HiddenResource:
    """Found hidden resource."""

    url: str
    is_document: bool
    source_page: str


class DocumentFinder:
    """Class for finding documents on a website."""

    def __init__(self: "DocumentFinder") -> None:
        """Initialize DocumentFinder."""
        self.hidden_resources: list[HiddenResource] = []

    def find_documents(self: "DocumentFinder", pages: list[ParsedPage]) -> None:
        """Find document links on the provided pages."""
        for page in pages:
            for link in page.links:
                if self._is_document(link):
                    resource = HiddenResource(
                        url=link,
                        is_document=True,
                        source_page=page.url,
                    )
                    self.hidden_resources.append(resource)

    def _is_document(self: "DocumentFinder", url: str) -> bool:
        """Check if a URL is a document link."""
        document_extensions = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")
        return url.lower().endswith(document_extensions)
