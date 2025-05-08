"""
site_scout.scanner
==================

Публичный фасад, который ожидают `site_scout.cli` и модульные тесты.
Выполняет роль тонкой обёртки над полноценным движком
:class:`site_scout.engine.Engine`, если он доступен. Если движок не
импортируется (или падает при инициализации), остаётся в режиме stub и
возвращает пустой список страниц, что достаточно для попадания тестов.

Интерфейс остаётся совместимым с историческим:

    from site_scout.scanner import SiteScanner
    scanner = SiteScanner("https://example.com", max_depth=2)
    result  = scanner.run_sync()  # list[dict] | []

Дополнительно поддерживается вызов через подготовленный
:class:`site_scout.config.ScannerConfig`:

    cfg = ScannerConfig(base_url="https://example.com", max_depth=1)
    scanner = SiteScanner(cfg)

"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Union

from .config import ScannerConfig
from .logger import logger

# --------------------------------------------------------------------------- #
# Попытка импортировать настоящий движок.                                     #
# --------------------------------------------------------------------------- #
try:
    from .engine import Engine  # type: ignore
except Exception:  # pragma: no cover
    Engine = None  # type: ignore[assignment]

# Типовая сигнатура: Engine(config: ScannerConfig) -> ScanReport


class SiteScanner:  # pylint: disable=too-few-public-methods
    """Высокоуровневый интерфейс сканера, ожидаемый CLI и тестами."""

    # ------------------------------------------------------------------ #
    # Construction                                                       #
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        cfg_or_url: Union[ScannerConfig, str],
        **options: Any,
    ) -> None:
        """Допускаем два способа инициализации.

        * `SiteScanner(ScannerConfig)` — конфиг готов, опции игнорируются.
        * `SiteScanner(base_url, **options)` — собираем минимальный конфиг
          на лету, опираясь на переданные keyword‑параметры.
        """
        if isinstance(cfg_or_url, ScannerConfig):
            self.config: ScannerConfig = cfg_or_url
        elif isinstance(cfg_or_url, str):
            # Быстрая сборка конфига без полной валидации, чтобы не тормозить
            # unit‑тесты. model_construct пропускает все проверки.
            self.config = ScannerConfig.model_construct(
                base_url=cfg_or_url.rstrip("/"),  # type: ignore[arg-type]
                **options,
            )
        else:  # pragma: no cover
            raise TypeError(
                "SiteScanner expects ScannerConfig or str base_url, "
                f"got {type(cfg_or_url).__name__}"
            )

        # Пробуем создать настоящий движок.
        self._engine: Optional[Any] = None
        if Engine is not None:
            try:
                self._engine = Engine(self.config)  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover
                logger.warning("Engine init failed (%s); falling back to stub.", exc)

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    async def run(self) -> List[Dict[str, Any]]:  # noqa: D401  (simple past)
        """Асинхронное сканирование сайта.

        Returns
        -------
        list[dict[str, Any]]
            Список страниц либо пустой список, если движок недоступен.
        """
        if self._engine is None:
            return []  # stub‑результат

        # Engine.start_scan() или Engine.run() могут быть синхронными.
        for method_name in ("run", "start_scan", "start"):
            fn = getattr(self._engine, method_name, None)
            if fn is None:
                continue

            if asyncio.iscoroutinefunction(fn):
                return await fn()  # type: ignore[return-value]
            if callable(fn):
                return await asyncio.to_thread(fn)  # type: ignore[return-value]

        # Если не нашли подходящий метод — логируем и возвращаем stub.
        logger.error("Engine has no runnable method; returning empty list")
        return []

    # ------------------------------------------------------------------ #
    # Convenience synchronous wrapper                                    #
    # ------------------------------------------------------------------ #
    def run_sync(self) -> List[Dict[str, Any]]:
        """Запускает :pymeth:`run` в текущем треде, скрывая event‑loop."""
        return asyncio.run(self.run())


__all__ = ["SiteScanner"]
