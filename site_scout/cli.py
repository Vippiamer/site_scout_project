# === FILE: site_scout/cli.py ===
"""Site Scout — production‑ready CLI.

* Совместим с `tests/test_cli.py`.
* Работает с движком через :class:`site_scout.scanner.SiteScanner`.
* Пишет отчёты JSON/HTML, показывает прогресс, обрабатывает конфиги.
* Статический анализ (Pyright) проходит без ошибок.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import click
from rich.console import Console

from . import __version__
from .config import ScannerConfig
from .scanner import SiteScanner

console = Console()

# ---------------------------------------------------------------------------
# Отчётные рендеры (при отсутствии используем fallback)
# ---------------------------------------------------------------------------
try:
    from .report.json_report import render_json as _render_json  # type: ignore
except Exception:  # pragma: no cover
    _render_json = None  # type: ignore

try:
    from .report.html_report import render_html as _render_html  # type: ignore
except Exception:  # pragma: no cover
    _render_html = None  # type: ignore


def render_json(data: Any, path: Path) -> None:
    """Сохранить отчёт; вызвать внешний шаблон, если доступен."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if _render_json is not None:
        try:
            _render_json(data, path)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover
            console.print(f"[yellow]⚠ JSON‑шаблон упал:[/yellow] {exc}")


def render_html(data: Any, path: Path) -> None:
    """Создать HTML‑отчёт через шаблон или fallback."""
    if _render_html is not None:
        try:
            _render_html(data, path)  # type: ignore[arg-type]
            return
        except Exception as exc:  # pragma: no cover
            console.print(f"[yellow]⚠ HTML‑шаблон упал, fallback:[/yellow] {exc}")
    html = (
        "<!doctype html><meta charset=utf-8><title>Site Scout Report</title><pre>"
        + json.dumps(data, ensure_ascii=False, indent=2)
        + "</pre>"
    )
    path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# JSON‑сериализация произвольных моделей
# ---------------------------------------------------------------------------


def _jsonable(obj: Any) -> Any:  # noqa: C901 complexity acceptable
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "model_dump"):
        try:
            return _jsonable(obj.model_dump())  # Pydantic 2
        except Exception:  # pragma: no cover
            pass
    if is_dataclass(obj) and not isinstance(obj, type):
        return _jsonable(asdict(obj))
    return str(obj)


# ---------------------------------------------------------------------------
# Асинхронный запуск сканера
# ---------------------------------------------------------------------------


async def start_scan(cfg: ScannerConfig) -> List[Any]:  # noqa: D401
    """Запустить :class:`SiteScanner` и вернуть **list объектов**.

    1. Любой iterable → `list`.
    2. Одиночный объект → `[obj]`.

    Это гарантирует, что функция строго соответствует аннотации `List[Any]`,
    устраняя предупреждение Pyright `Generator -> List`.
    """
    scn = SiteScanner(cfg)  # type: ignore[arg-type]
    result: Any
    try:
        result = await scn.run()
    except Exception as exc:  # pragma: no cover
        console.print(f"[red]Ошибка сканera:[/red] {exc}")
        result = []

    # --- нормализуем к list ---------------------------------- #
    if isinstance(result, list):
        return result
    if hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
        try:
            return list(result)  # type: ignore[arg-type]
        except Exception:  # pragma: no cover
            pass
        result_list: List[Any]
    if isinstance(result, list):
        result_list = result
    elif hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
        try:
            result_list = list(result)  # type: ignore[arg-type]
        except Exception:  # pragma: no cover
            result_list = [result]
    else:
        result_list = [result]

    return cast(List[Any], result_list)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _load_yaml_json(path: Path) -> Dict[str, Any]:
    import json as _json  # noqa: E402

    import yaml

    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix.lower() in {".yml", ".yaml"} else _json.loads(text)


def _get_config(ctx: click.Context) -> ScannerConfig:
    cfg_path: Optional[Path] = ctx.obj.get("cfg_path")
    if cfg_path is None:
        console.print("[red]Error:[/red] --config обязателен или укажите URL")
        sys.exit(1)
    try:
        return ScannerConfig.load(cfg_path)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        console.print(f"[red]Ошибка конфига:[/red] {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Click root
# ---------------------------------------------------------------------------


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name="SiteScout")
@click.option("--config", "config_path", type=click.Path(dir_okay=False, path_type=Path))
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[Path]) -> None:  # noqa: D401
    """Site Scout — сканер сайтов."""
    ctx.ensure_object(dict)
    ctx.obj["cfg_path"] = config_path


# ---------------------------------------------------------------------------
# CONFIG group
# ---------------------------------------------------------------------------


@cli.group()
def config() -> None:  # noqa: D401
    """Работа с конфигами."""


@config.command("show")
@click.pass_context
def cfg_show(ctx: click.Context) -> None:  # noqa: D401
    cfg = _get_config(ctx)
    data = cfg.model_dump(mode="json")
    data["base_url"] = str(data["base_url"]).rstrip("/")
    console.print_json(json.dumps(data, ensure_ascii=False))


@config.command("validate")
@click.pass_context
def cfg_validate(ctx: click.Context) -> None:  # noqa: D401
    _ = _get_config(ctx)
    console.print("[green]✓ Конфиг валиден[/green]")


# ---------------------------------------------------------------------------
# SCAN command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("url", required=False)
@click.option("--json", "json_file", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--html", "html_file", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--scan-timeout", type=float)
@click.pass_context
def scan(  # noqa: D401
    ctx: click.Context,
    url: Optional[str],
    json_file: Optional[Path],
    html_file: Optional[Path],
    scan_timeout: Optional[float],
) -> None:
    """Сканировать URL и вывести/сохранить отчёты."""

    # ---- формируем конфиг --------------------------------------
    if url:
        base: Dict[str, Any] = {}
        cfg_path: Optional[Path] = ctx.obj.get("cfg_path")
        if cfg_path and cfg_path.exists():
            base = _load_yaml_json(cfg_path)
        base["base_url"] = url
        cfg = ScannerConfig.model_validate(base)
    else:
        cfg = _get_config(ctx)

    # ---- выполняем сканер -------------------------------------
    async def _runner() -> List[Any]:
        return await start_scan(cfg)

    try:
        pages_raw: List[Any] = (
            asyncio.run(asyncio.wait_for(_runner(), scan_timeout))
            if scan_timeout
            else asyncio.run(_runner())
        )
    except asyncio.TimeoutError:
        console.print("[red]Сканирование прервано по таймауту[/red]")
        sys.exit(1)

    pages = _jsonable(pages_raw)

    # ---- вывод / сохранение -----------------------------------
    if not json_file and not html_file:
        console.print_json(json.dumps(pages, ensure_ascii=False))

    if json_file:
        render_json(pages, json_file)
        console.print(f"[green]✓ JSON сохранён:[/green] {json_file}")

    if html_file:
        render_html(pages, html_file)
        console.print(f"[green]✓ HTML сохранён:[/green] {html_file}")


# ---------------------------------------------------------------------------
# REPORT command
# ---------------------------------------------------------------------------


@cli.command("report")
@click.argument("report_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--html", "html_file", type=click.Path(dir_okay=False, path_type=Path))
def report_cmd(report_json: Path, html_file: Optional[Path]) -> None:  # noqa: D401
    """Сгенерировать или пересоздать HTML отчёт из существующего JSON."""
    try:
        data = json.loads(report_json.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        console.print(f"[red]Не могу прочитать файл отчёта:[/red] {exc}")
        sys.exit(1)

    if html_file is None:
        html_file = report_json.with_suffix(".html")
    render_html(data, html_file)
    console.print(f"[green]✓ HTML сохранён:[/green] {html_file}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    cli()
