# cli.py

"""
Точка входа для запуска сканера SiteScout через командную строку.

Функционал:
- Парсинг аргументов (config, json, html, шаблон)
- Загрузка конфигурации (Pydantic)
- Инициализация логирования
- Запуск асинхронного сканирования (Engine)
- Генерация отчётов (JSON и/или HTML)

Пример запуска:
    python cli.py --config configs/default.yaml --json reports/report.json --html reports/report.html --template templates
"""
import asyncio
import sys
from pathlib import Path

import click

from site_scout.config import load_config
from site_scout.logger import init_logging
from site_scout.engine import start_scan
from site_scout.report.json_report import render_json
from site_scout.report.html_report import render_html


@click.command()
@click.option(
    '--config', '-c',
    'config_path',
    default='configs/default.yaml',
    help='Путь к файлу конфигурации YAML.'
)
@click.option(
    '--json', '-j',
    'json_output',
    default=None,
    help='Путь для сохранения JSON-отчёта.'
)
@click.option(
    '--html', '-h',
    'html_output',
    default=None,
    help='Путь для сохранения HTML-отчёта.'
)
@click.option(
    '--template', '-t',
    'template_dir',
    default='templates',
    help='Папка с Jinja2-шаблонами для HTML.'
)
def main(config_path: str, json_output: str, html_output: str, template_dir: str):
    """
    CLI-запуск SiteScout.
    """
    # 1. Загрузка конфигурации
    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Ошибка загрузки конфигурации: {e}")
        sys.exit(1)

    # 2. Инициализация логирования
    logger = init_logging(level=config.user_agent if hasattr(config, 'user_agent') else 'INFO')
    logger.info(f"Конфигурация загружена: {config_path}")

    # 3. Запуск сканирования
    logger.info("Запуск сканирования...")
    try:
        scan_report = asyncio.run(start_scan(config))
    except Exception as e:
        logger.error(f"Ошибка при сканировании: {e}")
        sys.exit(1)

    # 4. Генерация отчётов
    if json_output:
        json_path = Path(json_output)
        saved_json = render_json(scan_report, json_path)
        logger.info(f"JSON-отчёт сохранён: {saved_json}")
        click.echo(f"JSON report: {saved_json}")

    if html_output:
        html_path = Path(html_output)
        saved_html = render_html(scan_report, template_dir, html_path)
        logger.info(f"HTML-отчёт сохранён: {saved_html}")
        click.echo(f"HTML report: {saved_html}")

    # 5. Завершение
    logger.info("SiteScout завершил работу.")


if __name__ == '__main__':
    main()