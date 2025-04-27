# === FILE: site_scout_project/site_scout/cli.py ===
"""Command-line interface for **SiteScout**.

Usage examples::

    python -m site_scout.cli scan --config configs/default.yaml \
        --json report.json

    sitescout scan --html report.html  # uses defaults (no config file)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from site_scout.engine import Engine
from site_scout.logger import logger

VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# root group                                                                  #
# --------------------------------------------------------------------------- #


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, exists=False, path_type=Path),
    help="YAML configuration file. If omitted, defaults are used.",
    default=None,
    show_default=True,
)
@click.option("--version", is_flag=True, help="Show version and exit.")
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[Path], version: bool) -> None:  # noqa: D401
    if version:
        click.echo(f"SiteScout version {VERSION}")
        ctx.exit()

    # store config-path (may be None) in context obj
    ctx.ensure_object(dict)
    ctx.obj["CONFIG_PATH"] = config_path


# --------------------------------------------------------------------------- #
# config command                                                              #
# --------------------------------------------------------------------------- #


@cli.command("config", help="Show effective configuration as JSON.")
@click.pass_context
def show_config(ctx: click.Context) -> None:  # noqa: D401
    cfg_path: Optional[Path] = ctx.obj.get("CONFIG_PATH")
    cfg = Engine.load_config(str(cfg_path) if cfg_path else None)
    click.echo(cfg.json(pretty=True))


# --------------------------------------------------------------------------- #
# scan command                                                                #
# --------------------------------------------------------------------------- #


@cli.command("scan", help="Run site scan and output report.")
@click.option(
    "--json",
    "json_out",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Write report as JSON to this file instead of stdout.",
)
@click.option(
    "--html",
    "html_out",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Write report as HTML to this file (overrides --json).",
)
@click.option(
    "--scan-timeout",
    type=float,
    help="Override request timeout configured in YAML/defaults.",
)
@click.pass_context
def scan_site(
    ctx: click.Context,
    json_out: Optional[Path],
    html_out: Optional[Path],
    scan_timeout: Optional[float],
) -> None:  # noqa: D401
    """Perform scan and dump report (JSON by default)."""
    cfg_path: Optional[Path] = ctx.obj.get("CONFIG_PATH")
    cfg = Engine.load_config(str(cfg_path) if cfg_path else None)

    if scan_timeout is not None:
        cfg.timeout = scan_timeout

    engine = Engine(cfg)
    raw_pages = engine.start_scan()
    report = engine.aggregate_results(raw_pages)

    # decide output format -------------------------------------------------- #
    if html_out is not None:
        html_out.write_text(report.generate_html(), encoding="utf-8")
        click.echo(str(html_out))
        return

    if json_out is not None:
        json_out.write_text(report.json(pretty=True), encoding="utf-8")
        click.echo(str(json_out))
        return

    # default – pretty JSON to stdout
    click.echo(report.json(pretty=True))


if __name__ == "__main__":  # pragma: no cover
    try:
        cli(obj={})
    except Exception as exc:  # catch-all for CLI usability
        logger.error("CLI error: %s", exc)
        sys.exit(1)
