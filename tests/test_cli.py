# tests/test_cli.py
"""
Тесты для CLI (`cli.py`) с использованием click.testing.CliRunner.
Проверяют команды `scan`, `config`, `--version`, а также обработку ошибок.
"""
import json
import asyncio
import pytest
from click.testing import CliRunner
from pathlib import Path

import site_scout.cli as cli_module
from site_scout.cli import cli
from site_scout.config import ScannerConfig
from site_scout.engine import start_scan
from site_scout.report.json_report import render_json
from site_scout.report.html_report import render_html


@pytest.fixture(autouse=True)
def patch_start_scan(monkeypatch):
    """
    Патчим start_scan, чтобы возвращать заранее заданный список страниц без реального сканирования.
    """
    class DummyPage:
        def __init__(self, url, content):
            self.url = url
            self.content = content
    dummy = [DummyPage('http://example.com/', '<html></html>')]
    async def fake_scan(cfg):
        return dummy
    monkeypatch.setattr(cli_module, 'start_scan', fake_scan)
    return dummy


@pytest.fixture(autouse=True)
def patch_reports(monkeypatch):
    """
    Патчим render_json и render_html для предсказуемости.
    """
    monkeypatch.setattr(cli_module, 'render_json', lambda data, path: str(path))
    monkeypatch.setattr(cli_module, 'render_html', lambda data, tpl, path: str(path))


def test_version_option():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert 'SiteScout' in result.output


def test_show_config(tmp_path, monkeypatch):
    # Подготовка временного default.yaml
    cfg_file = tmp_path / 'default.yaml'
    cfg_file.write_text(json.dumps({
        'base_url': 'https://example.com',
        'max_depth': 1,
        'timeout': 1.0,
        'user_agent': 'Agent/1.0',
        'rate_limit': 1.0,
        'retry_times': 0,
        'wordlists': {'paths': str(tmp_path/'p.txt'), 'files': str(tmp_path/'f.txt')}
    }))
    # Создаем словари
    (tmp_path/'p.txt').write_text('a')
    (tmp_path/'f.txt').write_text('b')
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ['--config', str(cfg_file), 'config'])
    assert result.exit_code == 0
    # JSON вывода должен содержать ключи
    data = json.loads(result.output)
    assert data['base_url'] == 'https://example.com'


def test_scan_stdout(tmp_path, monkeypatch):
    # Создаем корректный конфи
    cfg_file = tmp_path / 'config.yaml'
    cfg_file.write_text(json.dumps({
        'base_url': 'https://example.com',
        'max_depth': 1,
        'timeout': 1.0,
        'user_agent': 'Agent/1.0',
        'rate_limit': 1.0,
        'retry_times': 0,
        'wordlists': {'paths': str(tmp_path/'x.txt'), 'files': str(tmp_path/'y.txt')}
    }))
    (tmp_path/'x.txt').write_text('')
    (tmp_path/'y.txt').write_text('')
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ['--config', str(cfg_file), 'scan'])
    assert result.exit_code == 0
    # Строка JSON-вывода
    output = json.loads(result.output)
    assert isinstance(output, list)
    assert output[0]['url'] == 'http://example.com/'


def test_scan_json_file(tmp_path):
    # Проверка сохранения JSON в файл
    cfg = tmp_path/'config.yaml'
    cfg.write_text(json.dumps({
        'base_url': 'https://example.com', 'max_depth':1, 'timeout':1.0,
        'user_agent':'Agent','rate_limit':1.0,'retry_times':0,
        'wordlists':{'paths':str(tmp_path/'a.txt'),'files':str(tmp_path/'b.txt')}
    }))
    (tmp_path/'a.txt').write_text('')
    (tmp_path/'b.txt').write_text('')

    out = tmp_path/'out.json'
    runner = CliRunner()
    result = runner.invoke(cli, ['--config', str(cfg), 'scan', '--json', str(out)])
    assert result.exit_code == 0
    assert out.exists()
    # Проверяем содержимое
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data[0]['url'] == 'http://example.com/'


def test_scan_html_file(tmp_path):
    # Аналогично для HTML
    cfg = tmp_path/'config.yaml'
    cfg.write_text(json.dumps({
        'base_url': 'https://example.com', 'max_depth':1, 'timeout':1.0,
        'user_agent':'Agent','rate_limit':1.0,'retry_times':0,
        'wordlists':{'paths':str(tmp_path/'a.txt'),'files':str(tmp_path/'b.txt')}
    }))
    (tmp_path/'a.txt').write_text('')
    (tmp_path/'b.txt').write_text('')

    out = tmp_path/'report.html'
    runner = CliRunner()
    result = runner.invoke(cli, ['--config', str(cfg), 'scan', '--html', str(out)])
    assert result.exit_code == 0
    assert out.exists()


def test_scan_timeout(monkeypatch, tmp_path):
    # Патчим start_scan на долгую задачу
    async def slow(cfg): await asyncio.sleep(2); return []
    monkeypatch.setattr(cli_module, 'start_scan', slow)

    cfg = tmp_path/'config.yaml'
    cfg.write_text(json.dumps({
        'base_url': 'https://example.com', 'max_depth':1, 'timeout':1.0,
        'user_agent':'Agent','rate_limit':1.0,'retry_times':0,
        'wordlists':{'paths':str(tmp_path/'a'),'files':str(tmp_path/'b')}
    }))
    (tmp_path/'a').write_text('')
    (tmp_path/'b').write_text('')

    runner = CliRunner()
    result = runner.invoke(cli, ['--config', str(cfg), 'scan', '--scan-timeout', '1'])
    assert result.exit_code != 0
    assert 'не завершено' in result.output
