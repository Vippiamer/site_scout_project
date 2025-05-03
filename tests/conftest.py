# File: tests/conftest.py
import asyncio
from pathlib import Path
from typing import Dict

import pytest

from site_scout.config import ScannerConfig
from site_scout.crawler.models import PageData


@pytest.fixture()
def wordlists_files(tmp_path) -> Dict[str, Path]:
    """
    Create temporary wordlist files for tests.
    Returns dict with names to file paths.
    """
    files = tmp_path / "files.txt"
    paths = tmp_path / "paths.txt"
    files.write_text("word1\nword2")
    paths.write_text("/some/path\n/another/path")
    return {"files": files, "paths": paths}


@pytest.fixture()
def event_loop():
    """
    Create an instance of the default event loop for each test.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def basic_config(wordlists_files) -> ScannerConfig:
    """
    Return a basic valid ScannerConfig for crawler tests.
    """
    return ScannerConfig(
        base_url="http://example.com",
        max_depth=1,
        timeout=2.0,
        user_agent="TestAgent/1.0",
        rate_limit=5.0,
        wordlists=wordlists_files,
    )


@pytest.fixture()
def mock_page_data() -> PageData:
    """
    Provide a simple PageData instance with HTML content.
    """
    html = '<html><body><a href="/link1">L1</a><a href="http://external.com">X</a></body></html>'
    return PageData(url="http://example.com/", content=html)
