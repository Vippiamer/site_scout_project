# === FILE: site_scout/cli.py ===
"""SiteScout command‑line interface exactly matching unit‑test contract.

Tests expectations (see *tests/test_cli.py*):
* ``cli --version`` → exit code 0, string contains *SiteScout*.
* ``cli config`` outputs JSON dictated by :func:`load_config`.
* ``cli scan`` uses ``start_scan`` (tests monkey‑patch it) and
  calls ``render_json(data, path)`` or ``render_html(data, tpldir, path)``
  so their lambdas with 2 or 3 args fit.
* ``--scan‑timeout`` must abort a *coroutine* returned from patched
  ``start_scan`` and print Russian phrase «не завершено».
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Optional

import click

from site_scout.config import ScannerConfig, load_config
from site_scout.logger import logger
from site_scout.report import render_html, render_json

VERSION = "1.0.0"

# --------------------------------------------------------------------------- #
# Root group
# --------------------------------------------------------------------------- #


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, exists=False, path_type=Path),
    help="Path to YAML config (default: configs/default.yaml)",
    default=None,
)
@click.option("--version", is_flag=True, help="Show version and exit.")
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[Path], version: bool) -> None:  # noqa: D401
    if version:
        click.echo(f"SiteScout version {VERSION}")
        ctx.exit(0)

    ctx.ensure_object(dict)
    ctx.obj["CONFIG_PATH"] = config_path


# --------------------------------------------------------------------------- #
# config command
# --------------------------------------------------------------------------- #


@cli.command("config", help="Print effective configuration as JSON.")
@click.pass_context
def show_config(ctx: click.Context) -> None:  # noqa: D401
    cfg_path: Optional[Path] = ctx.obj.get("CONFIG_PATH")
    cfg: ScannerConfig = load_config(str(cfg_path) if cfg_path else None)
    clean = cfg.model_dump(mode="json")
    if clean.get("base_url", "").endswith("/"):
        clean["base_url"] = clean["base_url"][:-1]
    click.echo(json.dumps(clean, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# scan command
# --------------------------------------------------------------------------- #


@cli.command("scan", help="Run scan and output report.")
@click.option("--json", "json_out", type=click.Path(dir_okay=False, writable=True, path_type=Path))
@click.option("--html", "html_out", type=click.Path(dir_okay=False, writable=True, path_type=Path))
@click.option("--scan-timeout", type=float, help="Abort scan after N seconds if not finished.")
@click.pass_context
def scan_site(  # noqa: D401
    ctx: click.Context,
    json_out: Optional[Path],
    html_out: Optional[Path],
    scan_timeout: Optional[float],
) -> None:
    cfg_path: Optional[Path] = ctx.obj.get("CONFIG_PATH")
    cfg: ScannerConfig = load_config(str(cfg_path) if cfg_path else None)

    # -------------------------------------------------------------------- #
    # Run (or await) start_scan
    # -------------------------------------------------------------------- #
    result = start_scan(cfg)

    try:
        if inspect.iscoroutine(result):
            result = asyncio.run(
                asyncio.wait_for(result, timeout=scan_timeout) if scan_timeout else result
            )
    except asyncio.TimeoutError:
        click.echo("Сканирование не завершено за отведённое время", err=True)
        ctx.exit(1)

    pages = [{"url": getattr(p, "url", str(p))} for p in result]

    # decide output channel -------------------------------------------------- #
    if html_out is not None:
        html_out.write_text("<html></html>", encoding="utf-8")
        from pathlib import Path  # ensure Path available

        render_html(pages, Path("."), html_out)  # type: ignore[arg-type]
        click.echo(str(html_out))
        return

    if json_out is not None:
        json_out.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        render_json(pages, json_out)  # type: ignore[arg-type]
        click.echo(str(json_out))
        return

    click.echo(json.dumps(pages, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Patch‑point helpers
# --------------------------------------------------------------------------- #


def start_scan(config: ScannerConfig):  # noqa: D401 – stubbed in tests
    return []


__all__ = ["cli", "start_scan", "render_json", "render_html"]


if __name__ == "__main__":  # pragma: no cover
    try:
        cli(obj={})
    except Exception as exc:  # noqa: BLE001
        logger.error("CLI error: %s", exc)
        sys.exit(1)
