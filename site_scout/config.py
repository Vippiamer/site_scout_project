# === FILE: site_scout_project/site_scout/config.py ===
"""SiteScout configuration handling.

Provides :class:`ScannerConfig` (validated settings) and :func:`load_config` that
searches for a *configs/default.yaml* in the *current working directory* first
(so tests can monkey‑patch *cwd*), then falls back to the packaged default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, root_validator, validator

__all__ = ["ScannerConfig", "load_config"]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_BUILTIN_DEFAULT = _PACKAGE_ROOT / "configs" / "default.yaml"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Wordlists(BaseModel):
    """Paths to wordlists used by brute‑forcer (may be omitted)."""

    paths: Optional[str] = None
    files: Optional[str] = None


class ScannerConfig(BaseModel):
    """Validated configuration for the SiteScout crawler."""

    # Mandatory
    base_url: str = Field(..., description="Root URL of the target website")

    # Optional – sane defaults
    max_depth: int = Field(2, ge=0)
    timeout: float = Field(5.0, gt=0)
    user_agent: str = Field("SiteScout/1.0")
    rate_limit: float = Field(1.0, gt=0)
    retry_times: int = Field(2, ge=0)

    # Added fields needed by crawler/tests
    concurrency: int = Field(10, ge=1)
    max_pages: Optional[int] = Field(None, ge=1)

    wordlists: Wordlists = Field(default_factory=Wordlists)

    class Config:
        extra = "forbid"
        validate_assignment = True

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @validator("base_url")
    def _validate_base_url(cls, v: str) -> str:  # noqa: N805 – pydantic naming
        v = v.rstrip("/")
        pr = urlparse(v)
        if pr.scheme not in {"http", "https"} or not pr.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        return v

    @root_validator
    def _check_wordlists_exist(cls, values):  # noqa: N805
        wl: Wordlists = values.get("wordlists")  # type: ignore[assignment]
        for label in ("paths", "files"):
            path = getattr(wl, label, None)
            if path and not Path(path).exists():
                raise FileNotFoundError(f"Wordlist '{path}' does not exist")
        return values


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_config_file(path: Path) -> dict:
    """Read YAML/JSON file and return dict."""
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    ext = path.suffix.lower()
    if ext in {".yaml", ".yml"}:
        return yaml.safe_load(text) or {}
    if ext == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported config extension: {ext}")


def load_config(path: Optional[Union[str, Path]] = None) -> ScannerConfig:
    """Load configuration.

    Order of precedence when *path* is *None*:
    1. ``$PWD/configs/default.yaml`` – allows tests to monkey‑patch cwd.
    2. Built‑in file bundled with the package.
    """
    if path is None:
        candidate = Path.cwd() / "configs" / "default.yaml"
        path = candidate if candidate.exists() else _BUILTIN_DEFAULT

    data = _read_config_file(Path(path))
    return ScannerConfig(**data)
