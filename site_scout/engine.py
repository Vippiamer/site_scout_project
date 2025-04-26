# site_scout/engine.py

"""
Оркестратор (Engine) проекта SiteScout.

Задачи модуля:
- Инициализация и управление asyncio-очередью URL для сканирования.
- Запуск и контроль асинхронных воркеров:
  - Crawler-корутин (сбор страниц и HTTP-данных)
  - Parser-корутин (разбор HTML/robots/sitemap)
  - DocFinder-корутин (поиск документов)
  - BruteForce-корутин (скрытые пути)
- Сбор сырых результатов от воркеров.
- Graceful shutdown (остановка воркеров по сигналу).
- Передача всех результатов в агрегатор для финального отчёта.
"""
import asyncio
import signal
from typing import List, Any

from site_scout.config import ScannerConfig
from site_scout.logger import init_logging
from site_scout.crawler.crawler import AsyncCrawler
from site_scout.parser.html_parser import parse_html
from site_scout.doc_finder import find_documents
from site_scout.bruteforce.brute_force import BruteForcer
from site_scout.aggregator import aggregate_results

# Количество параллельных воркеров (можно вынести в конфиг)
DEFAULT_WORKERS = 5


async def worker(
    name: str,
    queue: asyncio.Queue,
    results: List[Any],
    config: ScannerConfig,
    crawler: AsyncCrawler,
    bruteforcer: BruteForcer
):
    """
    Асинхронный воркер, который:
    1. Получает URL из очереди.
    2. Скачивает страницу (crawler.fetch_page).
    3. Парсит HTML (parse_html).
    4. Находит документы (find_documents).
    5. Производит brute-force (bruteforcer.scan_paths).
    6. Сохраняет результаты в общий список.
    7. Повторяет, пока не получит sentinel (None).

    :param name: имя воркера для логов
    :param queue: очередь URL для обработки
    :param results: общий список для хранения результатов
    :param config: настройки сканера
    :param crawler: экземпляр AsyncCrawler
    :param bruteforcer: экземпляр BruteForcer
    """
    logger = init_logging()
    while True:
        url = await queue.get()
        if url is None:
            # Sentinel: сигнал завершения
            queue.task_done()
            break

        logger.debug(f"[{name}] Обработка URL: {url}")
        try:
            # 1) Скачать страницу
            page_data = await crawler.fetch_page(url)
            # 2) Распарсить HTML
            parsed = parse_html(page_data)
            # 3) Найти документы
            docs = await find_documents(parsed)
            # 4) Brute-force скрытых путей
            hidden = await bruteforcer.scan_paths(url)
            # Сохранить результат
            results.append({
                'url': url,
                'parsed': parsed,
                'documents': docs,
                'hidden_paths': hidden
            })
        except Exception as e:
            logger.error(f"[{name}] Ошибка обработки {url}: {e}")
        finally:
            queue.task_done()


async def start_scan(config: ScannerConfig) -> Any:
    """
    Основная точка входа для запуска сканирования.

    Шаги:
    1. Инициализировать логгер.
    2. Подготовить очередь и seed-URL.
    3. Создать экземпляры AsyncCrawler и BruteForcer.
    4. Запустить воркеры.
    5. Подождать завершения очереди.
    6. Graceful shutdown воркеров через sentinel.
    7. Собрать результаты и передать в агрегатор.

    :param config: объект ScannerConfig с настройками
    :return: объект с агрегированными результатами (ScanReport)
    """
    # Инициализируем логгер
    logger = init_logging()
    logger.info("Запуск SiteScout Engine")

    # Создаём очередь URL
    queue: asyncio.Queue = asyncio.Queue()
    results: List[Any] = []

    # Инициализируем компоненты
    crawler = AsyncCrawler(config)
    bruteforcer = BruteForcer(config)

    # Добавляем стартовый URL
    await queue.put(config.base_url)

    # Запускаем воркеры
    workers = []
    for i in range(DEFAULT_WORKERS):
        name = f"worker-{i+1}"
        task = asyncio.create_task(
            worker(name, queue, results, config, crawler, bruteforcer)
        )
        workers.append(task)

    # Обработчик SIGINT/SIGTERM для graceful shutdown
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    # Ожидаем завершения очереди или сигнала
    await queue.join()
    logger.info("Очередь пустая, отправляем сигналы завершения воркерам...")

    # Посылаем sentinel (None) каждому воркеру
    for _ in workers:
        await queue.put(None)

    # Ждём завершения воркеров
    await asyncio.gather(*workers)
    logger.info("Все воркеры завершены")

    # Агрегация результатов
    report = aggregate_results(results)
    logger.info("Сканирование завершено, результаты агрегированы")
    return report


# Пример запуска модуля напрямую
if __name__ == "__main__":
    import sys
    from site_scout.config import load_config

    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml"
    config = load_config(config_path)

    # Запускаем сканирование
    scan_report = asyncio.run(start_scan(config))
    print(scan_report)  # или сохранить отчёт в файл
