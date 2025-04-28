# === FILE: site_scout/report/html_report.py ===
"""
Генерация HTML-отчёта для проекта SiteScout.

Использует Jinja2 для шаблонов и базовую визуализацию
карты сайта и списка документов.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from site_scout.aggregator import ScanReport


def render_html(
    report: ScanReport,
    template_dir: Path | str,
    output_path: Path | str,
) -> Path:
    """
    Рендерит HTML из шаблонов и сохраняет по указанному пути.

    :param report: объект ScanReport
    :param template_dir: директория с Jinja2-шаблонами
    :param output_path: путь к итоговому HTML-файлу
    :return: Path сохранённого HTML

    Пример:
    ```python
    from site_scout.report.html_report import render_html
    html_path = render_html(
        report,
        template_dir='templates',
        output_path='reports/report.html'
    )
    print(f"HTML report saved to: {html_path}")
    ```
    """
    # Преобразование путей
    template_dir = Path(template_dir)
    output_path = Path(output_path)
    # Создание директории для вывода, если не существует
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Настройка Jinja2 среды с автоэкранизацией
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    # Загрузка шаблона
    template = env.get_template("report.html.j2")

    # Подготовка контекста для шаблона
    context: dict[str, Any] = {
        "pages": report.pages,
        "documents": report.documents,
        "hidden_resources": report.hidden_resources,
        "locales": report.locales,
    }

    # Рендеринг и запись HTML
    html_content = template.render(**context)
    output_path.write_text(html_content, encoding="utf-8")

    return output_path
