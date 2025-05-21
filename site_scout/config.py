# === FILE: site_scout/config.py ===
"""
Модуль для загрузки и валидации конфигурации сканера SiteScout.
Используется Pydantic для описания схемы и проверки данных.
"""
from __future__ import annotations

import json
import os
import errno
from pathlib import Path
from typing import Any, Dict, Union

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    field_validator,
    model_validator,
)


class LocaleConfig(BaseModel):
    subdomain: str
    path_prefix: str
    hreflangs: list[str] = Field(default_factory=list)
    accept_languages: list[str] = Field(default_factory=list)


class ScannerConfig(BaseModel):
    """Конфигурация для одного запуска сканирования."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: HttpUrl = Field(..., description="Корневой URL для сканирования.")
    max_depth: int = Field(3, ge=0, description="Максимальная глубина обхода ссылок.")
    max_pages: int = Field(1000, ge=1, description="Жесткий лимит по числу страниц.")
    timeout: float = Field(10.0, gt=0, description="Таймаут на один запрос (секунд).")
    user_agent: str = Field("SiteScoutBot/1.0", min_length=1, description="Заголовок User-Agent.")
    rate_limit: float = Field(1.0, gt=0, description="Лимит запросов в секунду.")
    retry_times: int = Field(3, ge=0, description="Число повторных попыток при 5xx.")
    wordlists: Dict[str, str] = Field(..., description="Пути к файлам словарей.")

    localization: Dict[str, LocaleConfig] = Field(
        default_factory=dict, description="Настройки национальных сегментов."
    )

    @field_validator("base_url", mode="before")
    def _strip_trailing_slash(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.rstrip("/")
        return v

    @model_validator(mode="after")
    def _check_wordlists_exist(self) -> ScannerConfig:
        missing = [p for p in self.wordlists.values() if not Path(p).is_file()]
        if missing:
            # FileNotFoundError with filename
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), missing[0])
        return self


_DEFAULT_CFG = Path("configs/default.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Неправильный YAML в {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"Верхний уровень YAML должен быть mapping, получено {type(data).__name__}")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"Неправильный JSON в {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"Верхний уровень JSON должен быть mapping, получено {type(data).__name__}")
    return data


def load_config(path: Union[str, Path, None]) -> ScannerConfig:
    """
    Читает YAML или JSON и возвращает проверенный объект ScannerConfig.
    При отсутствии файла конфига или его словарей бросает FileNotFoundError.
    """
    if path is None:
        if not _DEFAULT_CFG.exists():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(_DEFAULT_CFG))
        path_obj = _DEFAULT_CFG
    else:
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.is_file():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(path_obj))

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
