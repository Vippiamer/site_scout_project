# === FILE: site_scout/scanner.py ===
"""
Модуль-обёртка, обеспечивающий функцию запуска сканирования.
"""
from typing import Any, List

from site_scout.config import ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler

async def start_scan(cfg: ScannerConfig) -> List[Any]:
    """
    Запускает асинхронный краулер и возвращает список страниц.

    Parameters
    ----------
    cfg : ScannerConfig
        Конфигурация сканирования.

    Returns
    -------
    List[Any]
        Список результатов страниц (модели Page).
    """
    crawler = AsyncCrawler(cfg)
    pages = await crawler.run()
    return pages

# Экспортируем для CLI и тестов
__all__ = ["start_scan"]
