# === FILE: site_scout_project/site_scout/cli.py ===
"""SiteScout – Click‑based command‑line interface.

> **Why Click?**  Project tests (`tests/test_cli.py`) rely on *click*’s
> `CliRunner`, so this module exports a *click* root command named **cli** that
> matches those expectations yet re‑uses internal library code.

Main responsibilities:
* Parse options (global and per‑command).
* Initialise logging once.
* Load/patch configuration (e.g. `--limit`).
* Delegate work to :pyfunc:`site_scout.engine.start_scan`.
* Emit JSON to stdout and/or write JSON/HTML reports.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from site_scout.config import ScannerConfig, load_config
from site_scout.engine import start_scan
from site_scout.logger import init_logging

# ---------------------------------------------------------------------------
# Optional reporting helpers (tests monkey‑patch these symbols!)
# ---------------------------------------------------------------------------

try:
    from site_scout.report.json_report import render_json  # type: ignore
except ModuleNotFoundError:  # pragma: no cover – optional dependency
    def render_json(data: Any, path: Path) -> None:  # type: ignore[override]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

try:
    from site_scout.report.html_report import render_html  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    def render_html(data: Any, template: Optional[Path], path: Path) -> None:  # type: ignore[override]
        path.write_text("<html><body><pre>HTML reporting disabled</pre></body></html>")

# ---------------------------------------------------------------------------
# Click root – global options shared by sub‑commands
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version="1.0.0", prog_name="SiteScout")
@click.option(
    "--config",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
    help="Путь к YAML/JSON конфигу; если опущен – используется configs/default.yaml",
)
@click.option("--limit", type=int, help="Жёсткий лимит количества страниц")
@click.option("--log-level", default="INFO", help="Уровень логирования (DEBUG/INFO/…)")
@click.option("--log-file", default="-", help="Файл логов или '-' для stdout")
@click.option("--log-format", default="%(asctime)s %(levelname)s %(message)s")
@click.pass_context
def cli(ctx: click.Context, **global_opts):  # noqa: D401
    """Root command that stores *global* options in the Click context."""

    # Logging first so that anything below is captured
    init_logging(
        level=global_opts.pop("log_level"),
        log_file=global_opts.pop("log_file"),
        fmt=global_opts.pop("log_format"),
    )

    cfg: ScannerConfig = load_config(global_opts.pop("config", None))
    limit: Optional[int] = global_opts.pop("limit", None)
    if limit:
        cfg.max_pages = limit  # type: ignore[assignment]

    # Save objects for sub‑commands
    ctx.ensure_object(dict)
    ctx.obj["CONFIG"] = cfg
    ctx.obj["GLOBAL_OPTS"] = global_opts  # keep anything else (future‑proof)


# ---------------------------------------------------------------------------
# Sub‑command: config – pretty‑print effective configuration
# ---------------------------------------------------------------------------


@cli.command(help="Показать итоговую конфигурацию и выйти")
@click.pass_context
def config(ctx: click.Context) -> None:  # noqa: D401
    cfg: ScannerConfig = ctx.obj["CONFIG"]
    click.echo(cfg.json(indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Sub‑command: scan – full site crawl & reporting
# ---------------------------------------------------------------------------


@cli.command(help="Запустить сканирование и сформировать отчёты")
@click.option("--json", "json_path", type=click.Path(path_type=Path), help="Сохранить JSON‑отчёт")
@click.option("--html", "html_path", type=click.Path(path_type=Path), help="Сохранить HTML‑отчёт (требует Jinja2)")
@click.option("--scan-timeout", type=float, default=None, help="Тайм‑аут сканирования (сек.)")
@click.pass_context
def scan(
    ctx: click.Context,
    json_path: Optional[Path],
    html_path: Optional[Path],
    scan_timeout: Optional[float],
) -> None:  # noqa: D401

    cfg: ScannerConfig = ctx.obj["CONFIG"]

    # ------------------------------------------------------------------
    # Run the asynchronous scan (respecting optional timeout)
    # ------------------------------------------------------------------
    try:
        coro = start_scan(cfg)
        report: Any
        if scan_timeout:
            report = asyncio.run(asyncio.wait_for(coro, timeout=scan_timeout))
        else:
            report = asyncio.run(coro)
    except asyncio.TimeoutError:
        click.echo("Сканирование не завершено за указанное время", err=True)
        ctx.exit(1)

    # ------------------------------------------------------------------
    # STDOUT – always emit JSON for piping / tests
    # ------------------------------------------------------------------
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------
    # Optional file outputs
    # ------------------------------------------------------------------
    if json_path:
        render_json(report, json_path)  # type: ignore[arg-type]

    if html_path:
        template: Optional[Path] = None  # reserved for future option
        render_html(report, template, html_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Entry‑point (python ‑m site_scout.cli …)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    cli()  # pylint: disable=no-value-for-parameter
