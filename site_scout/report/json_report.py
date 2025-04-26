# site_scout/report/json_report.py

"""
Генерация JSON-отчёта для проекта SiteScout.

Сериализация объекта ScanReport в файл.
"""
import json
from pathlib import Path
from site_scout.aggregator import ScanReport


def render_json(report: ScanReport, output_path: Path | str) -> Path:
    """
    Сохраняет отчёт report в формате JSON по указанному пути.

    :param report: объект ScanReport с данными сканирования
    :param output_path: путь к JSON-файлу
    :return: Path сохранённого файла

    Пример:
    ```python
    from site_scout.report.json_report import render_json
    report_path = render_json(report, 'reports/report.json')
    print(f"JSON report saved to: {report_path}")
    ```
    """
    # Приводим к Path
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Сериализация: dataclasses -> dict
    data = {
        'pages': report.pages,
        'documents': report.documents,
        'hidden_resources': report.hidden_resources,
        'locales': report.locales
    }

    # Запись в файл с отступами и Unicode
    with output.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output

