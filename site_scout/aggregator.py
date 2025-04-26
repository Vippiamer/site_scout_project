# site_scout/aggregator.py

"""
Модуль агрегатора для проекта SiteScout.

Задачи:
- Агрегация сырых данных от crawler, parser, doc_finder, bruteforce, localization.
- Нормализация и формирование единой структуры ScanReport.
- Предоставление API для доступа к собранным данным.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ScanReport:
    """
    Итоговый отчёт по сканированию сайта.
    Поля:
    - pages: список данных по каждой сканируемой странице
    - documents: список всех найденных документов
    - hidden_resources: список найденных скрытых ресурсов
    - locales: группировка URL по локалям
    - raw_results: необработанные результаты (для отладки)
    """
    pages: List[Dict[str, Any]] = field(default_factory=list)
    documents: List[Dict[str, Any]] = field(default_factory=list)
    hidden_resources: List[Dict[str, Any]] = field(default_factory=list)
    locales: Dict[str, List[str]] = field(default_factory=dict)
    raw_results: Any = None


def aggregate_results(raw_results: List[Dict[str, Any]]) -> ScanReport:
    """
    Преобразует список сырых результатов от воркеров в объект ScanReport.

    :param raw_results: список dict, где каждый dict содержит:
        - 'url'
        - 'parsed': ParsedPage
        - 'documents': list[DocumentInfo]
        - 'hidden_paths': list[HiddenResource]
    :return: ScanReport с нормализованными данными
    """
    report = ScanReport()
    report.raw_results = raw_results

    for entry in raw_results:
        # 1) Страницы и парсинг
        parsed = entry.get('parsed')
        page_info = {
            'url': entry.get('url'),
            'links': getattr(parsed, 'links', []),
            'meta': getattr(parsed, 'meta', {}),
            'headings': getattr(parsed, 'headings', {}),
            'headers': getattr(parsed, 'headers', {})
        }
        report.pages.append(page_info)

        # 2) Документы
        docs = entry.get('documents', [])
        for doc in docs:
            report.documents.append({
                'name': getattr(doc, 'name', ''),
                'url': getattr(doc, 'url', ''),
                'size': getattr(doc, 'size', 0),
                'mime': getattr(doc, 'mime', '')
            })

        # 3) Скрытые ресурсы
        hidden = entry.get('hidden_paths', [])
        for hr in hidden:
            report.hidden_resources.append({
                'url': getattr(hr, 'url', ''),
                'status': getattr(hr, 'status', None),
                'type': getattr(hr, 'content_type', ''),
                'size': getattr(hr, 'size', 0)
            })

    # 4) Локализация: если raw_results содержит ключ 'locales'
    # Предполагаем, что локализация собирается отдельно
    if raw_results and isinstance(raw_results[0], dict) and 'locales' in raw_results[0]:
        # Берём последнюю запись
        locs = raw_results[-1].get('locales', {})
        report.locales = {k: list(v) for k, v in locs.items()}

    return report

# Пример использования
if __name__ == '__main__':
    # raw_results — результат работы engine.start_scan()
    sample = [
        {
            'url': 'https://example.com',
            'parsed': None,
            'documents': [],
            'hidden_paths': [],
            'locales': {'jp': {'https://jp.example.com'}}
        }
    ]
    report = aggregate_results(sample)
    print(report)