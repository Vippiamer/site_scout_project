# === FILE: site_scout_project/site_scout/logger.py ===
"""Site‑wide logging configuration for the **SiteScout** project.

Highlights
----------
* Unified format for console and optional file output (with rotation).
* Single, importable instance :data:`logger` – simply::

      from site_scout.logger import logger
      logger.info("Scanning started")
* Re‑configurable at runtime via :func:`configure`.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final, Union

# --------------------------------------------------------------------------- #
# Constants & basic types                                                     #
# --------------------------------------------------------------------------- #

_DEFAULT_FORMAT: Final[str] = "%(_ asctime)s | %(levelname)-8s | %(name)s | %(message)s".replace(
    "_ ", ""
)
_LOGGER_NAME: Final[str] = "SiteScout"

_LevelT = Union[int, str]


# --------------------------------------------------------------------------- #
# Helper builders                                                             #
# --------------------------------------------------------------------------- #


def _stdout_handler(fmt: str) -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    return handler


def _file_handler(file: Path | str, fmt: str) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        filename=str(file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(fmt))
    return handler


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def configure(
    *,
    level: _LevelT = "INFO",
    log_file: str | Path | None = None,
    log_format: str = _DEFAULT_FORMAT,
    replace_handlers: bool = True,
) -> logging.Logger:
    """(Re)configure the global project logger.

    Parameters
    ----------
    level
        Numeric or textual logging level (e.g. ``"DEBUG"``).
    log_file
        Path to a logfile. *None* → console‑only output.
    log_format
        Format string for :class:`logging.Formatter`.
    replace_handlers
        *True* – remove existing handlers; *False* – just append new one(s).
    """
    lg = logging.getLogger(_LOGGER_NAME)
    lg.setLevel(level)

    if replace_handlers:
        lg.handlers.clear()

    lg.addHandler(_stdout_handler(log_format))

    if log_file is not None:
        lg.addHandler(_file_handler(log_file, log_format))

    lg.propagate = False
    return lg


def init_logging(
    level: _LevelT = "INFO", log_file: str | Path | None = "site_scout.log"
) -> logging.Logger:
    """Backward‑compatible alias used by legacy code."""
    return configure(level=level, log_file=log_file, replace_handlers=True)


# --------------------------------------------------------------------------- #
# Ready‑to‑use instance                                                       #
# --------------------------------------------------------------------------- #

logger: logging.Logger = init_logging()

__all__ = ["logger", "configure", "init_logging"]
