# === FILE: site_scout_project/tests/test_config.py ===
"""Тесты для модуля site_scout/config.py
Проверяют загрузку и валидацию конфигурации.
"""
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from site_scout.config import ScannerConfig, load_config


def write_yaml(tmp_path: Path, data: dict) -> Path:
    """Вспомогательная функция для записи словаря в YAML-файл и возврата пути к нему."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    return config_file


def test_load_valid_config_missing_base_url(tmp_path: Path):
    """Отсутствие base_url приводит к ValidationError."""
    paths = tmp_path / "paths.txt"
    files = tmp_path / "files.txt"
    paths.write_text("admin\nlogin", encoding="utf-8")
    files.write_text("secret.pdf", encoding="utf-8")

    data = {
        # base_url пропущен
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent/1.0",
        "rate_limit": 1.0,
        "retry_times": 0,
        "wordlists": {"paths": str(paths), "files": str(files)},
    }
    config_path = write_yaml(tmp_path, data)
    with pytest.raises(ValidationError) as exc:
        load_config(config_path)
    assert "base_url" in str(exc.value)


def test_invalid_base_url(tmp_path: Path):
    """Некорректный base_url вызывает ValidationError."""
    paths = tmp_path / "paths.txt"
    files = tmp_path / "files.txt"
    paths.write_text("", encoding="utf-8")
    files.write_text("", encoding="utf-8")

    data = {
        "base_url": "not_a_url",
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent/1.0",
        "rate_limit": 1.0,
        "retry_times": 0,
        "wordlists": {"paths": str(paths), "files": str(files)},
    }
    config_path = write_yaml(tmp_path, data)
    with pytest.raises(ValidationError):
        load_config(config_path)


def test_nonexistent_wordlist_paths(tmp_path: Path):
    """Отсутствие файлов в wordlists вызывает FileNotFoundError."""
    data = {
        "base_url": "https://example.com",
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent/1.0",
        "rate_limit": 1.0,
        "retry_times": 0,
        "wordlists": {
            "paths": "/nonexistent/paths.txt",
            "files": "/nonexistent/files.txt",
        },
    }
    config_path = write_yaml(tmp_path, data)
    with pytest.raises(FileNotFoundError) as exc:
        load_config(config_path)
    assert "nonexistent" in str(exc.value)


def test_load_default_when_missing(tmp_path: Path, monkeypatch):
    """Если конфиг не указан и default.yaml отсутствует, ожидаем FileNotFoundError."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_config(None)


def test_successful_load_default(tmp_path: Path, monkeypatch):
    """Если default.yaml есть, load_config без аргументов его загружает."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    default = configs_dir / "default.yaml"
    default.write_text(
        yaml.safe_dump(
            {
                "base_url": "https://example.com",
                "max_depth": 0,
                "timeout": 1.0,
                "user_agent": "Agent/1.0",
                "rate_limit": 1.0,
                "retry_times": 0,
                "wordlists": {"paths": str(tmp_path / "p.txt"), "files": str(tmp_path / "f.txt")},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "p.txt").write_text("a", encoding="utf-8")
    (tmp_path / "f.txt").write_text("b", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cfg = load_config(None)
    assert isinstance(cfg, ScannerConfig)
