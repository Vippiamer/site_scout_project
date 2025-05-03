# File: site_scout/report/html_report.py
"""site_scout.report.html_report: Генерация HTML-отчёта с помощью Jinja2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from jinja2 import Environment, FileSystemLoader, select_autoescape

from site_scout.aggregator import ScanReport


def render_html(
    report: ScanReport,
    template_dir: Union[Path, str],
    output_path: Union[Path, str],
) -> Path:
    """Рендерит HTML-отчёт из шаблона и сохраняет его по указанному пути.

    Args:
        report: объект ScanReport.
        template_dir: директория с Jinja2-шаблонами.
        output_path: путь к итоговому HTML-файлу.

    Returns:
        Path до сохранённого HTML-файла.

    Пример:
    ```python
    from site_scout.report.html_report import render_html
    html_path = render_html(
        report,
        template_dir='templates',
        output_path='reports/report.html'
    )
    ```
    """
    template_dir = Path(template_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html.j2")

    context: dict[str, Any] = {
        "pages": report.pages,
        "documents": report.documents,
        "hidden_resources": report.hidden_resources,
        "locales": report.locales,
    }

    html_content = template.render(**context)
    output_path.write_text(html_content, encoding="utf-8")

    return output_path
