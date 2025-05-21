# === FILE: site_scout/cli.py ===
#!/usr/bin/env python3
"""
Точка входа для запуска сканера SiteScout через командную строку.

Команды:
  scan      Запустить сканирование по конфигу и вывести/сохранить отчёты
  config    Показать текущую конфигурацию

Общие опции:
  --config PATH       Путь к YAML-конфигу (default: configs/default.yaml)
  --limit INT         Макс. число страниц для сканирования (override max_pages)
  --log-level LEVEL   Уровень логирования (DEBUG, INFO, ...)
  --log-file PATH     Файл для логов (stdout, если не указан)
  --log-format FORMAT Формат логирования (e.g. "%(asctime)s %(levelname)s %(message)s")

Команда scan опции:
  --json PATH         Сохранить JSON-отчёт в файл
  --html PATH         Сохранить HTML-отчёт в файл
  --template DIR      Папка с Jinja2-шаблонами
  --pretty            Преформатировать JSON-вывод (отступ 2)
  --scan-timeout SEC  Таймаут всего сканирования (секунд)

Дополнительно:
  --version, -v       Показать версию SiteScout

Пример:
  site_scout scan --config configs/default.yaml --json report.json --pretty --limit 100
"""
import sys
import asyncio
import json
from pathlib import Path

import click

from site_scout import __version__
from site_scout.config import load_config
from site_scout.logger import init_logging
from site_scout.engine import start_scan
from site_scout.report.json_report import render_json
from site_scout.report.html_report import render_html

CONTEXT_SETTINGS = dict(help_option_names=["--help"])

def print_error(message: str):
    click.secho(message, fg='red', err=True)
    sys.exit(1)

@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, '--version', '-v', message='SiteScout, version %(version)s')
@click.option(
    '--config', '-c', 'config_path',
    default='configs/default.yaml',
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help='Путь к файлу конфигурации YAML.'
)
@click.option(
    '--limit', '-l', 'limit',
    type=int,
    default=None,
    help='Макс. число страниц для сканирования (override max_pages)'
)
@click.option(
    '--log-level', 'log_level',
    default='INFO', show_default=True,
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
    help='Уровень логирования'
)
@click.option(
    '--log-file', 'log_file',
    default=None,
    type=click.Path(writable=True, dir_okay=False, path_type=Path),
    help='Путь к файлу логов (stdout, если не указан)'
)
@click.option(
    '--log-format', 'log_format',
    default='%(asctime)s %(levelname)s %(message)s',
    show_default=True,
    help='Строка формата для логов'
)
@click.pass_context
def cli(ctx, config_path, limit, log_level, log_file, log_format):
    """Группа команд SiteScout CLI."""
    init_logging(
        level=log_level,
        log_file=str(log_file) if log_file else None,
        log_format=log_format
    )
    try:
        cfg = load_config(config_path)
    except Exception as e:
        print_error(f'Ошибка загрузки конфигурации: {e}')
    if limit is not None:
        cfg.max_pages = limit
    ctx.ensure_object(dict)
    ctx.obj['config'] = cfg

@cli.command('scan', context_settings=CONTEXT_SETTINGS)
@click.option(
    '--json', '-j', 'json_output',
    default=None,
    type=click.Path(writable=True, dir_okay=False, path_type=Path),
    help='Сохранить JSON-отчёт в файл'
)
@click.option(
    '--html', '-h', 'html_output',
    default=None,
    type=click.Path(writable=True, dir_okay=False, path_type=Path),
    help='Сохранить HTML-отчёт в файл'
)
@click.option(
    '--template', '-t', 'template_dir',
    default='templates',
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help='Папка с Jinja2-шаблонами'
)
@click.option(
    '--pretty', is_flag=True,
    help='Преформатировать JSON-вывод (отступ 2)'
)
@click.option(
    '--scan-timeout', 'scan_timeout',
    type=float,
    default=None,
    help='Таймаут всего сканирования (секунд)'
)
@click.pass_context
def scan(ctx, json_output, html_output, template_dir, pretty, scan_timeout):
    """Запустить сканирование и сгенерировать отчёты."""
    cfg = ctx.obj['config']
    click.echo(f'Starting scan with config: {cfg.base_url}')
    try:
        if scan_timeout:
            pages = asyncio.run(
                asyncio.wait_for(start_scan(cfg), timeout=scan_timeout)
            )
        else:
            pages = asyncio.run(start_scan(cfg))
    except asyncio.TimeoutError:
        print_error(f'Сканирование не завершено за {scan_timeout} секунд')
    except Exception as e:
        print_error(f'Ошибка при сканировании: {e}')

    results = [{'url': p.url, 'content': p.content} for p in pages]

    # Если не сохраняем в файл — печатаем в stdout
    if not json_output and not html_output:
        indent = 2 if pretty else None
        try:
            click.echo(json.dumps(results, ensure_ascii=False, indent=indent))
        except TypeError as e:
            print_error(f'Ошибка сериализации JSON: {e}')
        return

    # JSON-отчёт
    if json_output:
        try:
            saved_json = render_json(results, json_output)
            click.echo(f'JSON report: {saved_json}')
        except Exception as e:
            print_error(f'Ошибка при сохранении JSON: {e}')

    # HTML-отчёт
    if html_output:
        try:
            saved_html = render_html(results, template_dir, html_output)
            click.echo(f'HTML report: {saved_html}')
        except Exception as e:
            print_error(f'Ошибка при сохранении HTML: {e}')

@cli.command('config', context_settings=CONTEXT_SETTINGS)
@click.pass_context
def show_config(ctx):
    """Показать текущую конфигурацию в JSON."""
    cfg = ctx.obj['config']
    click.echo(cfg.json(indent=2, ensure_ascii=False))

# expose these names at module level for test monkey-patching
cli.start_scan = start_scan
cli.render_json = render_json
cli.render_html = render_html

if __name__ == "__main__":
    cli()
