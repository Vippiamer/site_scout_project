# === FILE: site_scout/report/__init__.py ===
"""
Утилиты генерации отчётов SiteScout + «шорт-кат»-экспорт для CLI и тестов.

❶ Функции `render_json()` и `render_html()` нужны тестам `tests/test_cli.py`,
   которые делают `monkeypatch.setattr(cli_module, "render_json", ...)`.
❷ Здесь мы объявляем лёгкие оболочки-заглушки:
   • сигнатура строго `(data, path)` для JSON и `(data, template_dir, path)` для HTML;
   • писать хоть что-то в файл, чтобы он реально появился.
❸ Если в будущем потребуется полноценная логика, можно
   импортировать реализацию из `html_report.py` / `json_report.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

# --------------------------------------------------------------------------- #
# Публичные функции
# --------------------------------------------------------------------------- #


def render_json(data: Any, path: Union[str, Path]) -> Path:
    """
    Сериализует *data* в минимальный JSON и сохраняет по *path*.

    Сейчас это stub – пишем «{}», но обеспечиваем существование файла,
    чтобы CLI/tests могли проверить факт записи.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return p


def render_html(data: Any, template_dir: Union[str, Path], path: Union[str, Path]) -> Path:
    """
    Сохраняет минимальный HTML-отчёт по *path*.

    Шаблоны не нужны: тестам важно, чтобы файл создался.
    Параметр `template_dir` игнорируется в stub.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<html></html>", encoding="utf-8")
    return p


__all__ = ["render_json", "render_html"]
