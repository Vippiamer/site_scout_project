# tests/test_cli.py
"""
Тесты для CLI (`cli.py`) с использованием click.testing.CliRunner.

Покрывают:

* опцию `--version`;
* команду `config`;
* команду `scan` c выводом в stdout / JSON-файл / HTML-файл;
* прерывание длительного сканирования по таймауту.

Все вспомогательные действия (подготовка конфигов, патчи и т. д.)
вынесены в отдельные фикстуры для уменьшения дублирования кода
и повышения читаемости.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Callable, List

import pytest
import yaml
from click.testing import CliRunner

import site_scout.cli as cli_module
from site_scout.cli import cli


# --------------------------------------------------------------------------- #
#                                   helpers                                   #
# --------------------------------------------------------------------------- #
@pytest.fixture
def dummy_pages() -> List[object]:
    """Возвращает список фиктивных страниц, который подменяет реальный результат сканирования."""

    class DummyPage:  # pylint: disable=too-few-public-methods
        def __init__(self, url: str, content: str) -> None:
            self.url = url
            self.content = content

        def to_dict(self) -> dict[str, str]:
            """Приводим к виду, ожидаемому CLI при json.dumps()."""
            return {"url": self.url, "content": self.content}

        # Click вызывает `json.dumps(obj, default=lambda o: o.__dict__)`
        # поэтому достаточно атрибутов.
        __dict__ = property(lambda self: {"url": self.url, "content": self.content})  # type: ignore

    return [DummyPage("http://example.com/", "<html></html>")]


@pytest.fixture
def patch_start_scan(monkeypatch: pytest.MonkeyPatch, dummy_pages: List[object]) -> List[object]:
    """Подменяет real `start_scan` быстрой корутиной, возвращающей фиктивные страницы."""

    async def fake_scan(_cfg):  # pylint: disable=unused-argument
        return dummy_pages

    monkeypatch.setattr(cli_module, "start_scan", fake_scan, raising=True)
    return dummy_pages


@pytest.fixture
def patch_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет генераторы отчётов без сохранения контента."""

    def _stub(*args, **kwargs):  # noqa: D401
        """Возвращает путь последним позиционным аргументом, игнорируя остальные."""
        # Рендер может вызываться как render_json(data, path) либо render_html(data, tpl, path)
        return str(args[-1])

    monkeypatch.setattr(cli_module, "render_json", _stub, raising=True)
    monkeypatch.setattr(cli_module, "render_html", _stub, raising=True)


@pytest.fixture
def make_config(tmp_path: Path) -> Callable[..., Path]:
    """
    Возвращает фабрику `create_config(**kwargs) -> Path`,
    которая создаёт валидный YAML-конфиг с минимально-необходимыми полями,
    а также пустые файлы словарей.
    """

    def _create_config(
        *,
        file_name: str = "config.yaml",
        base_url: str = "https://example.com",
        depth: int = 1,
    ) -> Path:
        cfg_path = tmp_path / file_name
        wordlists = {
            "paths": tmp_path / "paths.txt",
            "files": tmp_path / "files.txt",
        }
        # Пишем пустые словари.
        for wl in wordlists.values():
            wl.write_text("", encoding="utf-8")

        cfg_data = {
            "base_url": base_url,
            "max_depth": depth,
            "timeout": 1.0,
            "user_agent": "Agent/1.0",
            "rate_limit": 1.0,
            "retry_times": 0,
            "wordlists": {k: str(v) for k, v in wordlists.items()},
        }
        cfg_path.write_text(yaml.safe_dump(cfg_data, sort_keys=False), encoding="utf-8")
        return cfg_path

    return _create_config


# --------------------------------------------------------------------------- #
#                                   tests                                     #
# --------------------------------------------------------------------------- #
def test_version_option() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.exception is None
    assert re.search(r"SiteScout.+\d+\.\d+\.\d+", result.output)


def test_show_config(make_config: Callable[..., Path]) -> None:
    cfg_file = make_config()

    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg_file), "config"])

    assert result.exit_code == 0
    assert result.exception is None

    data = json.loads(result.output)
    assert data["base_url"] == "https://example.com"
    # Проверяем наличие всех ключей из конфига.
    for key in ("max_depth", "timeout", "user_agent", "rate_limit", "retry_times", "wordlists"):
        assert key in data


def test_scan_stdout(
    tmp_path: Path,
    make_config: Callable[..., Path],
    patch_start_scan: List[object],
    patch_reports,  # noqa: PT001
) -> None:
    cfg_file = make_config()

    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg_file), "scan"])

    assert result.exit_code == 0
    assert result.exception is None

    output = json.loads(result.output)
    assert isinstance(output, list)
    assert output and output[0]["url"] == "http://example.com/"


def test_scan_json_file(
    tmp_path: Path,
    make_config: Callable[..., Path],
    patch_start_scan: List[object],
    patch_reports,  # noqa: PT001
) -> None:
    cfg_file = make_config()
    out_file = tmp_path / "out.json"

    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg_file), "scan", "--json", str(out_file)])

    assert result.exit_code == 0
    assert result.exception is None
    assert out_file.exists()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data[0]["url"] == "http://example.com/"


def test_scan_html_file(
    tmp_path: Path,
    make_config: Callable[..., Path],
    patch_start_scan: List[object],
    patch_reports,  # noqa: PT001
) -> None:
    cfg_file = make_config()
    out_file = tmp_path / "report.html"

    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg_file), "scan", "--html", str(out_file)])

    assert result.exit_code == 0
    assert result.exception is None
    assert out_file.exists()

    html_text = out_file.read_text(encoding="utf-8").lower()
    assert "<html" in html_text and "</html" in html_text


def test_scan_timeout(
    monkeypatch: pytest.MonkeyPatch,
    make_config: Callable[..., Path],
    tmp_path: Path,
    patch_reports,  # noqa: PT001
) -> None:
    """Эмулируем бесконечное сканирование и убеждаемся, что CLI обрывает его по таймауту."""

    async def never_finishes(_cfg):  # pylint: disable=unused-argument
        await asyncio.Future()

    monkeypatch.setattr(cli_module, "start_scan", never_finishes, raising=True)

    cfg_file = make_config()
    runner = CliRunner()
    # Ставим маленький таймаут, чтобы тест выполнялся быстро (< 100 мс)
    result = runner.invoke(cli, ["--config", str(cfg_file), "scan", "--scan-timeout", "0.1"])

    assert result.exit_code != 0
    # В CLI должен подняться ClickException или аналогичная ошибка.
    assert result.exception is not None
    # Проверяем, что в сообщении присутствует слово «таймаут» (на любом языке),
    # чтобы убедиться, что причина именно в прерывании операции.
    assert re.search(r"timeout|таймаут|не завершено", result.output, re.IGNORECASE)
