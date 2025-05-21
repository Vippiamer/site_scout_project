# === FILE: site_scout/scanner.py ===
"""
Модуль-обёртка для функции запуска сканирования.
"""
from typing import Any, List
from site_scout.crawler.crawler import AsyncCrawler


async def start_scan(cfg) -> List[Any]:
    """
    Запускает асинхронный краулер в контексте и возвращает список PageData.

    Parameters
    ----------
    cfg : ScannerConfig
        Конфигурация сканирования.

    Returns
    -------
    List[Any]
        Список результатов сканирования (модели PageData).
    """
    async with AsyncCrawler(cfg) as crawler:
        pages = await crawler.crawl()
    return pages

__all__ = ["start_scan"]
