# File: tests/test_config.py
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from site_scout.config import ScannerConfig, load_config


def write_file(tmp_path: Path, content: str, suffix: str) -> Path:
    path = tmp_path / f"config{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "content,loader,expect_exc",
    [
        ("base_url: http://example.com\nwordlists: {}", load_config, None),
        (json.dumps({"base_url": "http://example.com", "wordlists": {}}), load_config, None),
        ("{}", load_config, ValidationError),
        ("not: a: mapping", load_config, ValueError),
        ("::invalid yaml", load_config, TypeError),
    ],
)
def test_load_config_variants(tmp_path, content, loader, expect_exc):
    # Write YAML or JSON based on content
    suffix = ".yaml" if not content.strip().startswith("{") else ".json"
    cfg_path = write_file(tmp_path, content, suffix)
    if expect_exc:
        with pytest.raises(expect_exc):
            loader(cfg_path)
    else:
        cfg = loader(cfg_path)
        assert isinstance(cfg, ScannerConfig)
        # Strip trailing slash for comparison
        assert str(cfg.base_url).rstrip("/") == "http://example.com"


def test_load_config_default_missing(tmp_path, monkeypatch):
    # Ensure default file missing
    monkeypatch.chdir(tmp_path)
    default = Path("configs/default.yaml")
    if default.exists():
        default.unlink()
    with pytest.raises(FileNotFoundError):
        load_config(None)


def test_wordlists_file_not_found(tmp_path):
    # Nonexistent wordlists path triggers FileNotFoundError
    cfg_path = write_file(
        tmp_path, "base_url: http://example.com\nwordlists: {a: missing.txt}", ".yaml"
    )
    with pytest.raises(FileNotFoundError):
        load_config(cfg_path)
