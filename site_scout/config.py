# site_scout/config.py
"""
Модуль для загрузки и валидации конфигурации сканера SiteScout.
Используется Pydantic для описания схемы и проверки данных.
"""
from pathlib import Path
import yaml
from pydantic import BaseModel, HttpUrl, Field, validator


def _ensure_path(path_str: str) -> Path:
    """
    Преобразует строку в Path и проверяет существование файла.
    """
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {p}")
    return p

class ScannerConfig(BaseModel):
    """
    Схема конфигурации сканера.

    Атрибуты:
      - base_url: стартовый URL для обхода
      - max_depth: глубина рекурсии ссылок
      - timeout: таймаут запросов (сек)
      - user_agent: заголовок HTTP User-Agent
      - rate_limit: максимальная частота запросов (запросов в секунду)
      - retry_times: количество повторных попыток при ошибках 5xx
      - wordlists: словари для brute-force (paths и files)
    """
    base_url: HttpUrl = Field(..., description="Стартовый URL для сканирования")
    max_depth: int = Field(3, ge=0, le=10, description="Максимальная глубина рекурсии")
    timeout: float = Field(10.0, gt=0, description="Таймаут HTTP-запросов в секундах")
    user_agent: str = Field("SiteScoutBot/1.0", min_length=5, description="User-Agent для запросов")
    rate_limit: float = Field(1.0, gt=0, description="Частота запросов (зап/сек)")
    retry_times: int = Field(0, ge=0, description="Повторы при HTTP-ошибках 5xx")
    wordlists: dict[str, Path] = Field(..., description="Словари для brute-force: 'paths' и 'files'")

    @validator("wordlists", pre=True)
    def _validate_wordlists(cls, v):
        """
        Конвертирует строки в Path и проверяет наличие файлов.
        Ожидается словарь {'paths': '...', 'files': '...'}.
        """
        if not isinstance(v, dict) or not v:
            raise ValueError("wordlists должно быть непустым словарем")
        converted: dict[str, Path] = {}
        for key, val in v.items():
            converted[key] = _ensure_path(val)
        return converted


def load_config(path: str | Path | None = None) -> ScannerConfig:
    """
    Загружает конфигурацию из YAML-файла.
    Если path не указан или файл не найден, пытается использовать 'configs/default.yaml'.
    """
    if path is None:
        config_path = Path("configs/default.yaml")
    else:
        config_path = Path(path)
        if not config_path.exists():
            fallback = Path("configs/default.yaml")
            if fallback.exists():
                config_path = fallback
            else:
                raise FileNotFoundError(f"Конфиг не найден: {path}")
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ScannerConfig(**data)


if __name__ == "__main__":
    import sys
    try:
        cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
        print(cfg.json(indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
