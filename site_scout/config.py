"""
site_scout/config.py

Модуль для загрузки и валидации конфигурации сканера SiteScout.
Используется Pydantic для описания схемы и проверки данных.
"""
from pathlib import Path
import yaml
from pydantic import BaseModel, HttpUrl, Field, validator


def _ensure_path(path_str: str) -> Path:
    """
    Преобразует строку в объект Path и проверяет существование файла.
    """
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Файл конфигурации не найден: {p}")
    return p

class ScannerConfig(BaseModel):
    """
    Описание полей конфигурации сканера.
    """
    base_url: HttpUrl = Field(..., description="Стартовый URL для сканирования")
    max_depth: int = Field(3, ge=1, le=10,
                            description="Максимальная глубина рекурсии")
    timeout: float = Field(10.0, gt=0,
                            description="Тайм-аут HTTP-запросов в секундах")
    user_agent: str = Field("SiteScoutBot/1.0", min_length=5,
                            description="Заголовок User-Agent для запросов")
    rate_limit: float = Field(1.0, gt=0,
                              description="Частота запросов (запросов в секунду)")
    wordlists: dict[str, Path] = Field(...,
                                      description="Словари для brute-force сканирования")

    @validator("wordlists", pre=True)
    def _validate_and_convert_paths(cls, v):
        """
        Проверка наличия и преобразование путей в Path.
        Ожидается словарь вида {"paths": ".../paths.txt", "files": ".../files.txt"}.
        """
        if not isinstance(v, dict) or not v:
            raise ValueError("Словари для brute-force должны быть указаны в виде непустого словаря")
        converted = {}
        for name, path_str in v.items():
            converted[name] = _ensure_path(path_str)
        return converted


def load_config(path: Path | str) -> ScannerConfig:
    """
    Загружает конфигурацию из YAML-файла и возвращает объект ScannerConfig.

    Параметры:
        path: путь к YAML-файлу конфигурации

    Пример использования:
    ```python
    from site_scout.config import load_config

    config = load_config("configs/default.yaml")
    print(config.base_url)
    print(config.wordlists["paths"])
    ```

    Возвращает:
        ScannerConfig — валидированный объект с настройками.
    """
    # Проверяем и конвертируем путь к файлу
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")

    # Загружаем YAML
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Создаем объект конфигурации
    return ScannerConfig(**raw)


# Если запустить файл напрямую — показать пример
if __name__ == "__main__":
    import sys
    try:
        cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml")
        print(cfg.json(indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
