# site_scout/logger.py

"""
Модуль: site_scout/logger.py

Настройка логирования для проекта SiteScout.
- Вывод в консоль и в файл одновременно.
- Поддержка уровней DEBUG, INFO, WARNING, ERROR.
- Форматирование с таймстемпом, уровнем и источником события.
- Гибкая поддержка пользовательского формата логов.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

def init_logging(
    log_file: str = "site_scout.log",
    level: str = "INFO",
    log_format: Optional[str] = None
) -> logging.Logger:
    """
    Инициализирует и возвращает настроенный логгер.

    Параметры:
        log_file: Путь к файлу для записи логов.
        level:    Уровень логирования ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        log_format: Формат логов. Если не указан, используется стандартный.

    Возвращает:
        logging.Logger — экземпляр логгера с двумя хендлерами.
    """
    logger = logging.getLogger("SiteScout")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Удаляем старые хендлеры, если они были (чтобы не дублировать вывод)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Форматтер логов
    if log_format is None:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    formatter = logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # 1) Консольный хендлер
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logger.level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2) Файловый хендлер с ротацией
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logger.level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Пример использования
if __name__ == "__main__":
    log = init_logging(log_file="site_scout_debug.log", level="DEBUG")
    log.debug("DEBUG: тестовое сообщение")
    log.info("INFO: сканирование начато")
    log.warning("WARNING: небольшой сбой, но продолжаем")
    log.error("ERROR: ошибка при обработке страницы")