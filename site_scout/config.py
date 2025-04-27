# === FILE: site_scout_project/site_scout/config.py ===
"""
Configuration loader/validator for **SiteScout**.

Provides a typed ``ScannerConfig`` object that tests instantiate
directly (``ScannerConfig(base_url="…", …)``) *and* via helper
:func:`load_config` / :meth:`ScannerConfig.load_from_file`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

import yaml  # type: ignore[import]

__all__ = [
    "ConfigError",
    "ScannerConfig",
    "load_config",
]


class ConfigError(RuntimeError):
    """Raised when configuration is missing or malformed."""


class ScannerConfig:
    """Typed configuration wrapper with sensible defaults.

    Accepts either a mapping or keyword arguments; kwargs override
    mapping values.
    """

    # --------------------------------------------------------------------- #
    # construction                                                          #
    # --------------------------------------------------------------------- #

    def __init__(self, data: Mapping[str, Any] | None = None, **kwargs: Any) -> None:
        merged: Dict[str, Any] = {**(data or {}), **kwargs}

        # required
        self.base_url: str = str(merged.get("base_url", ""))

        # optional knobs
        self.max_depth: int = int(merged.get("max_depth", 3))
        self.max_pages: int = int(merged.get("max_pages", 1_000))
        self.timeout: float = float(merged.get("timeout", 10.0))
        self.user_agent: str = str(merged.get("user_agent", "SiteScoutBot/1.0"))
        self.rate_limit: float = float(merged.get("rate_limit", 1.0))
        self.retry_times: int = int(merged.get("retry_times", 3))
        self.wordlists: Dict[str, str] = dict(merged.get("wordlists", {}))

        # derived
        self.base_domain: str = Path(self.base_url).anchor or ""

        self._validate()

    # --------------------------------------------------------------------- #
    # validation                                                            #
    # --------------------------------------------------------------------- #

    def _validate(self) -> None:  # noqa: D401
        if not self.base_url:
            raise ConfigError("'base_url' is required in the configuration.")
        if not isinstance(self.wordlists, dict):
            raise ConfigError("'wordlists' must be a mapping of name → path.")

    # --------------------------------------------------------------------- #
    # serialisation helpers                                                 #
    # --------------------------------------------------------------------- #

    def as_dict(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "timeout": self.timeout,
            "user_agent": self.user_agent,
            "rate_limit": self.rate_limit,
            "retry_times": self.retry_times,
            "wordlists": self.wordlists,
        }

    def json(self, *, pretty: bool = False) -> str:
        """Return JSON representation."""
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2 if pretty else None)

    # --------------------------------------------------------------------- #
    # dunder helpers                                                        #
    # --------------------------------------------------------------------- #

    def __repr__(self) -> str:  # pragma: no cover
        kv = ", ".join(f"{k}={v!r}" for k, v in self.as_dict().items())
        return f"{self.__class__.__name__}({kv})"

    # --------------------------------------------------------------------- #
    # class helpers required by tests/engine                                #
    # --------------------------------------------------------------------- #

    @classmethod
    def load_from_file(cls, path: str | Path | None) -> "ScannerConfig":
        """Factory wrapper around :func:`load_config`."""
        return load_config(path)


# --------------------------------------------------------------------------- #
# public loader                                                               #
# --------------------------------------------------------------------------- #


def load_config(path: str | Path | None) -> ScannerConfig:
    """Load YAML config. *None* → default config."""
    if path is None:
        return ScannerConfig()

    cfg_path = Path(path).expanduser()
    if not cfg_path.exists():
        raise ConfigError(f"Config file not found: {cfg_path}")

    try:
        with cfg_path.open(encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except yaml.YAMLError as exc:  # pragma: no cover
        raise ConfigError(f"YAML parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("Top-level YAML structure must be a mapping.")

    return ScannerConfig(data)
