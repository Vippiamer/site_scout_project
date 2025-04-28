# site_scout/engine.py
"""High-level orchestration layer for SiteScout.

The engine ties together:
* config loading
* crawler execution with timeout handling
* results aggregation
"""
from __future__ import annotations

import asyncio
from typing import List, Any, Optional

from site_scout.config import load_config, ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler
from site_scout.aggregator import ScanReport, aggregate_results
from site_scout.logger import logger

__all__ = ["Engine"]


class Engine:
    """Facade used by CLI and tests to run scans and aggregate results."""

    @staticmethod
    def load_config(path: Optional[str]) -> ScannerConfig:
        """Load YAML/JSON config or defaults when path is None."""
        return load_config(path)

    def __init__(self, config: ScannerConfig):
        self.config = config

    def start_scan(self) -> ScanReport:
        """Run asynchronous crawl with timeout and return aggregated report."""
        logger.info("Starting scan…")

        async def _runner() -> List[Any]:
            # Ensure aiohttp session cleanup
            async with AsyncCrawler(self.config) as crawler:
                return await crawler.crawl()

        try:
            # Apply timeout to full crawling
            raw_results = asyncio.run(asyncio.wait_for(_runner(), timeout=self.config.timeout))
        except asyncio.TimeoutError:
            logger.error("Scanning did not finish within %s seconds", self.config.timeout)
            raise
        except Exception as exc:
            logger.error("Scanning failed: %s", exc)
            raise

        try:
            # Convert raw page data into final report structure
            return aggregate_results(raw_results)
        except Exception as exc:
            logger.error("Aggregation failed: %s", exc)
            raise

    @staticmethod
    def aggregate_results(raw_results: List[Any]) -> ScanReport:
        """Aggregate raw page data into ScanReport."""
        return aggregate_results(raw_results)
