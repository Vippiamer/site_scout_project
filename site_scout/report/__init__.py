# File: site_scout/report/__init__.py
"""site_scout.report: Утилиты для генерации отчётов (JSON и HTML) используемые CLI и тестами."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union


def render_json(data: Any, path: Union[str, Path]) -> Path:
    """Сериализует data в JSON и сохраняет файл stub-отчёта по указанному пути."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return p


def render_html(data: Any, template_dir: Union[str, Path], path: Union[str, Path]) -> Path:
    """Сохраняет файл HTML-отчёта stub по указанному пути (игнорирует template_dir)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<html></html>", encoding="utf-8")
    return p


__all__ = ["render_json", "render_html"]
