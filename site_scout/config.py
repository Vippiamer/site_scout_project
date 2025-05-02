# site_scout/config.py
"""Configuration loading & validation for SiteScout.

Public API:

* ScannerConfig – pydantic-модель с описанием всех опций;
* load_config – читает YAML или JSON и возвращает проверенный ScannerConfig.

Тесты tests/test_config.py ожидают:
* Отсутствие обязательного поля base_url или некорректный URL вызывает ValidationError;
* Не существующие пути в параметре wordlists вызывают FileNotFoundError;
* Вызов load_config(None) без наличия default.yaml вызывает FileNotFoundError.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator


# Pydantic-модель конфигурации
class ScannerConfig(BaseModel):
    """Конфигурация для одного запуска сканирования."""

    # Обязательные параметры
    base_url: HttpUrl = Field(..., description="Корневой URL для сканирования.")

    # Настройки процесса сканирования
    max_depth: int = Field(3, ge=0, description="Максимальная глубина обхода ссылок.")
    max_pages: int = Field(1000, ge=1, description="Жесткий лимит по числу страниц.")
    timeout: float = Field(10.0, gt=0, description="Таймаут на один запрос (секунд).")
    user_agent: str = Field("SiteScoutBot/1.0", min_length=1, description="Заголовок User-Agent.")
    rate_limit: float = Field(1.0, gt=0, description="Лимит запросов в секунду.")
    retry_times: int = Field(3, ge=0, description="Число повторных попыток при 5xx.")

    # Пути к файлам словарей для обхода
    wordlists: Dict[str, Path] = Field(..., description="Пути к файлам словарей.")

    @model_validator(mode="after")
    def _check_wordlists_exist(self) -> ScannerConfig:
        missing = [str(p) for p in self.wordlists.values() if not Path(p).is_file()]
        if missing:
            raise FileNotFoundError("Отсутствуют файлы словарей: " + ", ".join(missing))
        return self

    class Config:
        extra = "forbid"
        frozen = True


_DEFAULT_CFG = Path("configs/default.yaml")

# Вспомогательные функции для чтения конфига


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Неправильный YAML в {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"Верхний уровень YAML должен быть mapping, получено {type(data).__name__}")
    return data


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"Неправильный JSON в {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"Верхний уровень JSON должен быть mapping, получено {type(data).__name__}")
    return data


def load_config(path: Union[str, Path, None]) -> ScannerConfig:
    """Читает YAML или JSON и возвращает проверенный объект ScannerConfig."""
    if path is None:
        if not _DEFAULT_CFG.exists():
            raise FileNotFoundError("default.yaml не найден и путь не задан")
        path_obj = _DEFAULT_CFG
    else:
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.is_file():
            raise FileNotFoundError(path_obj)

    suffix = path_obj.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = _read_yaml(path_obj)
    elif suffix == ".json":
        data = _read_json(path_obj)
    else:
        raise ValueError(f"Неподдерживаемый формат конфига: {suffix}")

    try:
        return ScannerConfig(**data)
    except ValidationError:
        raise
