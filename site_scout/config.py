# === FILE: site_scout/config.py
"""Configuration loading & validation for **SiteScout**.

The public surface consists of two symbols:

* :class:`ScannerConfig` – pydantic model describing all runtime options;
* :func:`load_config`     – helper that reads a YAML file (or the default
  ``configs/default.yaml``) and returns a validated :class:`ScannerConfig`.

Unit‑tests in *tests/test_config.py* rely on these exact behaviours:

* Missing ``base_url`` or malformed URL ⇒ *pydantic* ``ValidationError``.
* Non‑existent word‑list files ⇒ built‑in ``FileNotFoundError``.
* Calling ``load_config(None)`` with no default file present ⇒
  ``FileNotFoundError``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator

# --------------------------------------------------------------------------- #
# Public API exception ‑ tests expect *pydantic* ValidationError, therefore
# we do NOT define a custom subclass (would change isinstance‑checks).
# --------------------------------------------------------------------------- #


class ScannerConfig(BaseModel):
    """Validated runtime configuration for a single scan."""

    # Required ----------------------------------------------------------------
    base_url: HttpUrl = Field(..., description="Root URL to start crawling from.")

    # Optional tunables --------------------------------------------------------
    max_depth: int = Field(3, ge=0, description="Maximum link depth to crawl.")
    max_pages: int = Field(1000, ge=1, description="Hard page limit.")
    timeout: float = Field(10.0, gt=0, description="Per‑request timeout (sec).")
    user_agent: str = Field("SiteScoutBot/1.0", min_length=1)
    rate_limit: float = Field(1.0, gt=0, description="Max RPS.")
    retry_times: int = Field(3, ge=0, description="How many retries on 5xx.")

    # Word‑lists ---------------------------------------------------------------
    wordlists: Dict[str, Path] = Field(..., description="Paths to word‑lists.")

    # --------------------------------------------------------------------- #
    # Model‑level validation
    # --------------------------------------------------------------------- #

    @model_validator(mode="after")
    def _check_wordlists_exist(self) -> "ScannerConfig":  # noqa: D401
        missing: list[str] = [str(p) for p in self.wordlists.values() if not Path(p).is_file()]
        if missing:
            raise FileNotFoundError("Missing word‑list files: " + ", ".join(missing))
        return self

    # Permit ``config.json()`` w/o extra kwargs (tests call it)
    class Config:
        extra = "forbid"
        frozen = True


# --------------------------------------------------------------------------- #
# YAML loader helper
# --------------------------------------------------------------------------- #


_DEFAULT_CFG = Path("configs/default.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover – unlikely in tests
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"Top‑level YAML structure must be mapping, got {type(data).__name__}")
    return data


# --------------------------------------------------------------------------- #
# Public helper – used directly in tests
# --------------------------------------------------------------------------- #


def load_config(path: str | Path | None) -> ScannerConfig:
    """Read YAML *path* (or default) and return validated :class:`ScannerConfig`."""

    if path is None:
        if not _DEFAULT_CFG.exists():
            raise FileNotFoundError("default.yaml not found and path not provided")
        path = _DEFAULT_CFG

    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    data = _read_yaml(path)

    try:
        return ScannerConfig(**data)
    except ValidationError:
        # re‑raise as is – unit tests expect ValidationError exactly
        raise
