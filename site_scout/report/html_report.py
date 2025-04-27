# ----------------------------------------------
# site_scout/report/html_report.py

"""Генерация HTML-отчёта для проекта SiteScout.

Использует Jinja2 для шаблонов и базовую визуализацию
карты сайта и списка документов.
"""
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from site_scout.aggregator import ScanReport


def render_html(
    report: ScanReport,
    template_dir: Path | str,
    output_path: Path | str,
) -> Path:
    """Рендерит HTML из шаблонов и сохраняет по указанному пути.

    :param report: объект ScanReport
    :param template_dir: директория с Jinja2-шаблонами
    :param output_path: путь к итоговому HTML-файлу
    :return: Path сохранённого HTML

    Пример:
    ```python
    from site_scout.report.html_report import render_html
    report_path = render_html(
        report,
        template_dir='templates',
        output_path='reports/report.html'
    )
    print(f"HTML report saved to: {report_path}")
    ```
    """
    # Подготовка директорий
    template_dir = Path(template_dir)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Настройка Jinja2
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("report.html.j2")

    # Данные для шаблона
    context: dict[str, Any] = {
        "pages": report.pages,
        "documents": report.documents,
        "hidden_resources": report.hidden_resources,
        "locales": report.locales,
    }

    # Рендеринг и запись
    html = template.render(context)
    output.write_text(html, encoding="utf-8")
    return output


# ----------------------------------------------
# Пример шаблона Jinja2: templates/report.html.j2
#
# <!DOCTYPE html>
# <html lang="en">
# <head>
#   <meta charset="UTF-8">
#   <title>SiteScout Report</title>
#   <style>
#     body { font-family: Arial, sans-serif; margin: 20px; }
#     h1, h2 { color: #333; }
#     table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
#     th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
#     th { background: #f5f5f5; }
#   </style>
# </head>
# <body>
#   <h1>SiteScout Report</h1>
#   <h2>Сайты и страницы</h2>
#   <table>
#     <tr><th>URL</th><th>#Links</th><th>H1</th></tr>
#     {% for p in pages %}
#     <tr>
#       <td>{{ p.url }}</td>
#       <td>{{ p.links|length }}</td>
#       <td>{{ p.headings.h1|join(', ') }}</td>
#     </tr>
#     {% endfor %}
#   </table>
#   <h2>Документы</h2>
#   <table>
#     <tr><th>Name</th><th>Size</th><th>Type</th><th>URL</th></tr>
#     {% for d in documents %}
#     <tr>
#       <td>{{ d.name }}</td>
#       <td>{{ d.size }} bytes</td>
#       <td>{{ d.mime }}</td>
#       <td><a href="{{ d.url }}">{{ d.url }}</a></td>
#     </tr>
#     {% endfor %}
#   </table>
#   <h2>Скрытые ресурсы</h2>
#   <table>
#     <tr><th>URL</th><th>Status</th><th>Size</th></tr>
#     {% for h in hidden_resources %}
#     <tr>
#       <td><a href="{{ h.url }}">{{ h.url }}</a></td>
#       <td>{{ h.status }}</td>
#       <td>{{ h.size }}</td>
#     </tr>
#     {% endfor %}
#   </table>
#   <h2>Локали</h2>
#   <ul>
#     {% for loc, urls in locales.items() %}
#     <li>{{ loc }}: {{ urls|length }} URL</li>
#     {% endfor %}
#   </ul>
# </body>
# </html>
