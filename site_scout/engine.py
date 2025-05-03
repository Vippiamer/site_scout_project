# File: site_scout/engine.py
"""site_scout.engine: Orchestration layer для запуска сканирования и агрегации результатов."""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from site_scout.aggregator import ScanReport, aggregate_results
from site_scout.config import ScannerConfig, load_config
from site_scout.crawler.crawler import AsyncCrawler
from site_scout.logger import logger

__all__ = ["Engine"]


class Engine:
    """Фасад для CLI и тестов: загрузка конфига, запуск сканирования и агрегация результатов."""

    @staticmethod
    def load_config(path: Optional[str]) -> ScannerConfig:
        """Загружает конфиг из YAML/JSON или использует значения по умолчанию."""
        return load_config(path)

    def __init__(self, config: ScannerConfig) -> None:
        """Инициализирует Engine с заданной конфигурацией сканирования."""
        self.config = config

    def start_scan(self) -> ScanReport:
        """Запускает асинхронное сканирование с таймаутом и возвращает агрегированный отчёт."""
        logger.info("Starting scan…")

        async def _runner() -> List[Any]:
            """Внутренний корутин для запуска AsynсCrawler и сбора сырых данных."""
            async with AsyncCrawler(self.config) as crawler:
                return await crawler.crawl()

        try:
            raw_results = asyncio.run(asyncio.wait_for(_runner(), timeout=self.config.timeout))
        except asyncio.TimeoutError:
            logger.error("Scanning did not finish within %s seconds", self.config.timeout)
            raise
        except Exception as exc:
            logger.error("Scanning failed: %s", exc)
            raise

        try:
            return aggregate_results(raw_results)
        except Exception as exc:
            logger.error("Aggregation failed: %s", exc)
            raise

    @staticmethod
    def aggregate_results(raw_results: List[Any]) -> ScanReport:
        """Агрегирует сырые результаты в объект ScanReport через site_scout.aggregator."""
        return aggregate_results(raw_results)
