# === FILE: site_scout_project/site_scout/engine.py ===
"""SiteScout Engine – orchestrates the whole scanning pipeline.

Changes vs. previous version
----------------------------
* Uses `async with AsyncCrawler(...)` so that HTTP session is properly
  initialised and closed.
* Public `crawler.fetch_page()` helper (alias to internal fetch) keeps engine
  decoupled from crawler internals.
* Signal handling wrapped in *try/except NotImplementedError* for Windows and
  sub‑threads (`loop.add_signal_handler` not supported).
* Logging is configured **once** at start‑up; workers reuse the same logger.
"""
from __future__ import annotations

import asyncio
import signal
from typing import Any, List

from site_scout.aggregator import aggregate_results
from site_scout.bruteforce.brute_force import BruteForcer
from site_scout.config import ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler
from site_scout.logger import init_logging
from site_scout.parser.html_parser import parse_html
from site_scout.doc_finder import find_documents

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WORKERS = 5

# ---------------------------------------------------------------------------
# Worker coroutine
# ---------------------------------------------------------------------------


async def _worker(
    name: str,
    queue: "asyncio.Queue[str]",
    results: List[Any],
    crawler: AsyncCrawler,
    bruteforcer: BruteForcer,
) -> None:
    logger = init_logging()
    while True:
        url = await queue.get()
        if url is None:  # sentinel for graceful shutdown
            queue.task_done()
            break

        logger.debug("[%s] Обработка URL: %s", name, url)
        try:
            # 1) Download page
            page = await crawler.fetch_page(url)
            if not page:
                continue

            # 2) Parse html
            parsed = parse_html(page)

            # 3) Find documents
            docs = await find_documents(parsed)

            # 4) Hidden paths brute-force
            hidden = await bruteforcer.scan_paths(url)

            results.append(
                {
                    "url": url,
                    "parsed": parsed,
                    "documents": docs,
                    "hidden_paths": hidden,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] Ошибка обработки %s: %s", name, url, exc)
        finally:
            queue.task_done()


# ---------------------------------------------------------------------------
# Engine entrypoint
# ---------------------------------------------------------------------------


async def start_scan(config: ScannerConfig) -> Any:  # noqa: C901 (orchestrator)
    """Run full site scan and return aggregated report."""

    logger = init_logging()
    logger.info("Запуск SiteScout Engine")

    queue: asyncio.Queue[str] = asyncio.Queue()
    results: List[Any] = []

    # Seed URL
    await queue.put(config.base_url)

    async with AsyncCrawler(config) as crawler:
        bruteforcer = BruteForcer(config)

        # Worker pool
        workers = [
            asyncio.create_task(
                _worker(f"worker-{i+1}", queue, results, crawler, bruteforcer)
            )
            for i in range(DEFAULT_WORKERS)
        ]

        # Graceful shutdown on signals (works on UNIX main thread)
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except (NotImplementedError, RuntimeError):
                # Not available on Windows or non‑main thread – ignore
                pass

        # Wait until queue is empty or user interrupts
        await asyncio.wait(
            [queue.join(), stop_event.wait()],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Drain – send sentinel to workers
        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers)

    report = aggregate_results(results)
    logger.info("Сканирование завершено, результатов: %d", len(results))
    return report


# ---------------------------------------------------------------------------
# Script mode
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys

    from site_scout.config import load_config

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_config(cfg_path)

    summary = asyncio.run(start_scan(cfg))
    print(summary)
