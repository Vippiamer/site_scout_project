# === FILE: site_scout_project/tests/test_config.py ===
"""
Tests for ``site_scout_project/site_scout/config.py``.

They validate configuration loading logic, positive and negative paths,
and aim to stay robust across operating systems and Pydantic versions.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from pydantic import ValidationError

from site_scout.config import ScannerConfig, load_config


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _write_yaml(tmp_path: Path, data: Dict[str, Any]) -> Path:
    """
    Dump *data* to an ad-hoc YAML file inside *tmp_path* and return its path.

    A UUID is used to avoid filename clashes in parallel test runs.
    """
    file_path = tmp_path / f"config_{uuid.uuid4().hex}.yaml"
    file_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return file_path


def _assert_error_has_field(exc: ValidationError, field: str) -> None:
    """
    Assert that *field* is present in one of the ``ValidationError`` entries.

    Works with both Pydantic v1 and v2.
    """
    for err in exc.errors():
        loc = err.get("loc") or ()
        if isinstance(loc, (tuple, list)) and field in loc:
            return
    raise AssertionError(f"ValidationError does not reference {field!r}: {exc}")


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def sample_wordlists(tmp_path: Path) -> Dict[str, str]:
    """Create minimal word-list files and return them as a mapping."""
    paths_file = tmp_path / "paths.txt"
    files_file = tmp_path / "files.txt"
    paths_file.write_text("admin\nlogin", encoding="utf-8")
    files_file.write_text("secret.pdf", encoding="utf-8")
    return {"paths": str(paths_file), "files": str(files_file)}


@pytest.fixture()
def minimal_config(sample_wordlists: Dict[str, str]) -> Dict[str, Any]:
    """Return the smallest valid config dict; callers may mutate a copy."""
    return {
        "base_url": "https://example.com",
        "max_depth": 1,
        "timeout": 1.0,
        "user_agent": "Agent/1.0",
        "rate_limit": 1.0,
        "retry_times": 0,
        "wordlists": sample_wordlists,
    }


# --------------------------------------------------------------------------- #
# Negative scenarios                                                          #
# --------------------------------------------------------------------------- #
def test_missing_base_url_raises_validation_error(
    tmp_path: Path,
    minimal_config: Dict[str, Any],
) -> None:
    data = minimal_config.copy()
    data.pop("base_url")
    cfg_path = _write_yaml(tmp_path, data)

    with pytest.raises(ValidationError) as exc:
        load_config(cfg_path)

    _assert_error_has_field(exc.value, "base_url")


def test_invalid_base_url(tmp_path: Path, minimal_config: Dict[str, Any]) -> None:
    data = minimal_config | {"base_url": "not_a_url"}
    cfg_path = _write_yaml(tmp_path, data)

    with pytest.raises(ValidationError):
        load_config(cfg_path)


def test_nonexistent_wordlist_paths(tmp_path: Path, minimal_config: Dict[str, Any]) -> None:
    missing_paths = tmp_path / "does_not_exist_paths.txt"
    missing_files = tmp_path / "does_not_exist_files.txt"
    data = minimal_config | {
        "wordlists": {"paths": str(missing_paths), "files": str(missing_files)}
    }
    cfg_path = _write_yaml(tmp_path, data)

    with pytest.raises(FileNotFoundError) as exc:
        load_config(cfg_path)

    # The loader may fail on either path first; ensure one of them is reported.
    assert exc.value.filename in {str(missing_paths), str(missing_files)}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_depth", -1),
        ("timeout", 0),
        ("rate_limit", -0.1),
        ("retry_times", -1),
    ],
)
def test_invalid_numeric_values(
    tmp_path: Path,
    minimal_config: Dict[str, Any],
    field: str,
    value: Any,
) -> None:
    data = minimal_config.copy()
    data[field] = value
    cfg_path = _write_yaml(tmp_path, data)

    with pytest.raises(ValidationError):
        load_config(cfg_path)


# --------------------------------------------------------------------------- #
# Default-file scenarios                                                      #
# --------------------------------------------------------------------------- #
def test_load_default_when_missing(tmp_path: Path, monkeypatch) -> None:
    """
    If no config is supplied *and* ``configs/default.yaml`` is absent,
    ``load_config`` is expected to raise ``FileNotFoundError``.
    """
    # Ensure CWD has no configs/ directory.
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        load_config(None)


def test_successful_load_default(tmp_path: Path, monkeypatch) -> None:
    """
    When ``configs/default.yaml`` exists, ``load_config`` without arguments
    should load it successfully.
    """
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    default_cfg_path = configs_dir / "default.yaml"
    p_list = tmp_path / "p.txt"
    f_list = tmp_path / "f.txt"

    default_cfg_path.write_text(
        yaml.safe_dump(
            {
                "base_url": "https://example.com",
                "max_depth": 0,
                "timeout": 1.0,
                "user_agent": "Agent/1.0",
                "rate_limit": 1.0,
                "retry_times": 0,
                "wordlists": {"paths": str(p_list), "files": str(f_list)},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    p_list.write_text("a", encoding="utf-8")
    f_list.write_text("b", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    cfg = load_config(None)
    assert isinstance(cfg, ScannerConfig)


# --------------------------------------------------------------------------- #
# Positive custom-file scenario                                               #
# --------------------------------------------------------------------------- #
def test_successful_load_custom_config(
    tmp_path: Path, minimal_config: Dict[str, Any]
) -> None:
    """
    Loading an explicitly provided YAML with valid data should return
    a fully populated :class:`ScannerConfig` instance.
    """
    data = minimal_config | {
        "max_depth": 2,
        "timeout": 2.5,
        "user_agent": "Agent/2.0",
        "rate_limit": 0.5,
        "retry_times": 1,
    }
    cfg_path = _write_yaml(tmp_path, data)

    cfg = load_config(cfg_path)
    assert isinstance(cfg, ScannerConfig)

    # Compare primitives directly.  The *wordlists* field may be
    # a dict or a Pydantic sub-model; handle both cases.
    for key in ("base_url", "max_depth", "timeout", "user_agent", "rate_limit", "retry_times"):
        assert getattr(cfg, key) == data[key]

    if isinstance(cfg.wordlists, dict):
        assert cfg.wordlists == data["wordlists"]
    else:  # pragma: no cover
        # Fallback for dataclass / model object
        assert cfg.wordlists.paths == data["wordlists"]["paths"]
        assert cfg.wordlists.files == data["wordlists"]["files"]
