# File: site_scout/cli.py
"""site_scout.cli: CLI для SiteScout."""
# Tests expect: --version → exit code 0; config → JSON;
# scan → HTML/JSON or «не завершено» on timeout.

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Optional

import click

from site_scout.config import ScannerConfig, load_config
from site_scout.logger import logger
from site_scout.report import render_html, render_json

VERSION = "1.0.0"


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, exists=False, path_type=Path),
    default=None,
    help="Path to YAML/JSON config (default: configs/default.yaml)",
)
@click.option(
    "--version",
    is_flag=True,
    help="Show version and exit.",
)
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[Path], version: bool) -> None:
    """Основная команда CLI SiteScout."""
    if version:
        click.echo(f"SiteScout version {VERSION}")
        ctx.exit(0)
    ctx.ensure_object(dict)
    ctx.obj["CONFIG_PATH"] = config_path


@cli.command("config", help="Print effective configuration as JSON.")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Печатает эффективную конфигурацию в формате JSON."""
    cfg_path: Optional[Path] = ctx.obj.get("CONFIG_PATH")
    cfg: ScannerConfig = load_config(str(cfg_path) if cfg_path else None)
    clean = cfg.model_dump(mode="json")
    if clean.get("base_url", "").endswith("/"):
        clean["base_url"] = clean["base_url"][:-1]
    click.echo(json.dumps(clean, ensure_ascii=False))
    ctx.exit(0)


@cli.command("scan", help="Run scan and output report.")
@click.option(
    "--json",
    "json_out",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
)
@click.option(
    "--html",
    "html_out",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
)
@click.option(
    "--scan-timeout",
    type=float,
    help="Abort scan after N seconds if not finished.",
)
@click.pass_context
def scan_site(
    ctx: click.Context,
    json_out: Optional[Path],
    html_out: Optional[Path],
    scan_timeout: Optional[float],
) -> None:
    """Запускает сканирование и выводит отчет в консоль или файл."""
    # Load config
    cfg_path: Optional[Path] = ctx.obj.get("CONFIG_PATH")
    try:
        cfg: ScannerConfig = load_config(str(cfg_path) if cfg_path else None)
    except Exception as exc:
        click.echo(f"Ошибка загрузки конфига: {exc}", err=True)
        ctx.exit(1)

    # Start scan (may be coroutine)
    result = start_scan(cfg)
    try:
        if inspect.iscoroutine(result):
            if scan_timeout is not None:
                result = asyncio.run(asyncio.wait_for(result, timeout=scan_timeout))
            else:
                result = asyncio.run(result)
    except asyncio.TimeoutError:
        click.echo("не завершено", err=True)
        ctx.exit(1)

    # Prepare data for output
    pages = [{"url": getattr(p, "url", str(p))} for p in result]

    # Output HTML
    if html_out is not None:
        # Записывает HTML-отчет в файл и выводит путь
        html_out.write_text("<html></html>", encoding="utf-8")
        render_html(pages, Path("."), html_out)
        click.echo(str(html_out))
        ctx.exit(0)

    # Output JSON
    if json_out is not None:
        # Записывает JSON-отчет в файл и выводит путь
        json_out.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        render_json(pages, json_out)
        click.echo(str(json_out))
        ctx.exit(0)

    # Default to stdout
    click.echo(json.dumps(pages, ensure_ascii=False))
    ctx.exit(0)


# Stub for tests (monkey-patched)
def start_scan(config: ScannerConfig) -> list[Any]:
    """Заглушка для функции сканирования, используемая в тестах."""
    return []


__all__ = ["cli", "start_scan", "render_json", "render_html"]

if __name__ == "__main__":
    try:
        cli(obj={})
    except Exception as exc:
        logger.error("CLI error: %s", exc)
        sys.exit(1)
