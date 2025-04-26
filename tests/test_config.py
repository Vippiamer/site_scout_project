# tests/test_config.py

"""
Тесты для модуля site_scout/config.py
Проверяют загрузку и валидацию конфигурации.
"""
import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from site_scout.config import load_config, ScannerConfig


def write_yaml(tmp_path: Path, data: dict) -> str:
    """
    Вспомогательная функция для записи словаря в YAML-файл
    и возврата пути к нему.
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(config_file)


def test_load_valid_config(tmp_path: Path):
    """
    Конфигурация с корректными значениями должна загружаться без ошибок,
    и поля должны соответствовать входным данным.
    """
    # Подготовка фиктивных файлов словарей
    paths_file = tmp_path / "paths.txt"
    files_file = tmp_path / "files.txt"
    paths_file.write_text("admin\nlogin", encoding="utf-8")
    files_file.write_text("secret.pdf", encoding="utf-8")

    data = {
        # "base_url" пропущен
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent",
        "rate_limit": 1.0,
        # Используем реальные пути к файлам, чтобы проверить именно отсутствие base_url
        "wordlists": {"paths": str(paths_file), "files": str(files_file)}
    }
    config_path = write_yaml(tmp_path, data)
    with pytest.raises(ValidationError) as exc:
        load_config(config_path)
    # Сообщение об ошибке должно содержать имя отсутствующего поля
    assert 'base_url' in str(exc.value)


def test_invalid_base_url(tmp_path: Path):
    """
    Некорректное значение base_url (невалидный URL) должно привести к ValidationError.
    """
    # Создаем пустые файлы словаря для прохождения проверки путей
    paths_file = tmp_path / "paths.txt"
    files_file = tmp_path / "files.txt"
    paths_file.write_text("", encoding="utf-8")
    files_file.write_text("", encoding="utf-8")

    data = {
        "base_url": "not_a_valid_url",
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent",
        "rate_limit": 1.0,
        "wordlists": {"paths": str(paths_file), "files": str(files_file)}
    }
    config_path = write_yaml(tmp_path, data)
    with pytest.raises(ValidationError):
        load_config(config_path)


def test_nonexistent_wordlist(tmp_path: Path):
    """
    Если файлы из поля wordlists не существуют, должна быть ошибка FileNotFoundError.
    """
    data = {
        "base_url": "https://example.com",
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent",
        "rate_limit": 1.0,
        "wordlists": {
            "paths": "/nonexistent/paths.txt",
            "files": "/nonexistent/files.txt"
        }
    }
    config_path = write_yaml(tmp_path, data)
    with pytest.raises(FileNotFoundError) as exc_info:
        load_config(config_path)
    # Проверяем, что путь файла упомянут в исключении
    assert 'nonexistent' in str(exc_info.value)
