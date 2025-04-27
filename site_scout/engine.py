# === FILE: site_scout_project/site_scout/engine.py ===
"""High‑level orchestration layer for **SiteScout**.

The engine ties together:
* config loading
* crawler execution with timeout handling
* results aggregation
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from site_scout.aggregator import ScanReport, aggregate_results
from site_scout.config import ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler
from site_scout.logger import logger

__all__ = ["Engine"]


class Engine:
    """Convenience façade used by the CLI layer and tests."""

    # ------------------------------------------------------------------#
    # static helpers                                                    #
    # ------------------------------------------------------------------#
    @staticmethod
    def load_config(path: Optional[str]) -> ScannerConfig:  # noqa: D401
        """Load YAML config or obtain defaults when *path* is *None*."""
        return ScannerConfig.load_from_file(path)

    # ------------------------------------------------------------------#
    # construction                                                      #
    # ------------------------------------------------------------------#
    def __init__(self, config: ScannerConfig):
        self.config = config

    # ------------------------------------------------------------------#
    # scanning                                                          #
    # ------------------------------------------------------------------#
    def start_scan(self) -> List[dict]:  # noqa: D401 – return raw worker results
        """Run asynchronous crawl in a *synchronous* context and return raw data."""
        logger.info("Starting scan…")
        crawler = AsyncCrawler(self.config)

        async def _runner() -> List[dict]:
            async with crawler as c:  # opens aiohttp session
                await c.crawl()
                # Minimal mock for tests: return list of dicts with URLs only
                return [
                    {"url": url, "parsed": None, "documents": [], "hidden_paths": []}
                    for url in c.visited
                ]

        try:
            return asyncio.run(asyncio.wait_for(_runner(), timeout=self.config.timeout))
        except Exception as exc:  # pragma: no cover – surfaces to CLI/tests
            logger.error("Scanning failed: %s", exc)
            raise

    # ------------------------------------------------------------------#
    # aggregation                                                       #
    # ------------------------------------------------------------------#
    @staticmethod
    def aggregate_results(raw_results: List[dict]) -> ScanReport:  # noqa: D401
        """Aggregate raw worker results into :class:`ScanReport`."""
        return aggregate_results(raw_results)
