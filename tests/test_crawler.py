# File: tests/test_crawler.py
# Refactored test-suite for SiteScout async crawler
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from aiohttp import web
from site_scout.config import ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler


# --------------------------------------------------------------------------- #
#                            Pytest-configuration                              #
# --------------------------------------------------------------------------- #
def pytest_configure(config):
    """Register custom markers so that `--strict-markers` does not fail."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )


# --------------------------------------------------------------------------- #
#                               Helper utilities                              #
# --------------------------------------------------------------------------- #

#: number of seconds a “slow” handler sleeps in the concurrency test
SLOW_SLEEP: float = 0.5
#: number of pages created by the stress fixture / test (root + pages 1…200)
STRESS_PAGES: int = 201  # keeps test quick even on CI


def normalize_url(url: str) -> str:
    """Normalise *url* for comparison purposes: strip query, fragment, unify slash."""
    parts = urlsplit(url)
    path = parts.path
    if path and not path.endswith("/") and not Path(path).suffix:
        path += "/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


async def run_crawler(config: ScannerConfig, expected_pages: int = 100):
    """Run the crawler inside a timeout scaled by *expected_pages*."""
    total_timeout = max(15.0, expected_pages * 0.1)
    async with AsyncCrawler(config) as crawler:
        return await asyncio.wait_for(crawler.crawl(), timeout=total_timeout)


# --------------------------------------------------------------------------- #
#                                  Fixtures                                   #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def empty_wordlists(tmp_path: Path) -> dict[str, Path]:
    """Return dict with empty wordlist files."""
    paths_file = tmp_path / "paths.txt"
    files_file = tmp_path / "files.txt"
    paths_file.touch()
    files_file.touch()
    return {"paths": paths_file, "files": files_file}


async def _serve_app(app: web.Application, port: int) -> AsyncIterator[str]:
    """Start *app* on *port*, yield base URL, ensure cleanup."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", port)
    await site.start()
    try:
        yield f"http://localhost:{port}"
    finally:
        await runner.cleanup()


# --------------------------------------------------------------------------- #
#                            Test-server fixtures                             #
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def test_server_allow_all(unused_tcp_port: int) -> AsyncIterator[str]:
    app = web.Application()

    async def handle_root(_):
        return web.Response(text='<a href="/page1">Page1</a>', content_type="text/html")

    async def handle_page1(_):
        return web.Response(text='<a href="/page2">Page2</a>', content_type="text/html")

    async def handle_page2(_):
        return web.Response(text='<a href="/page3">Page3</a>', content_type="text/html")

    async def handle_page3(_):
        await asyncio.sleep(3)
        return web.Response(text="<h1>Page3 (slow)</h1>", content_type="text/html")

    async def handle_robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", handle_root)
    app.router.add_get("/page1", handle_page1)
    app.router.add_get("/page2", handle_page2)
    app.router.add_get("/page3", handle_page3)
    app.router.add_get("/robots.txt", handle_robots)

    async for url in _serve_app(app, unused_tcp_port):
        yield url


@pytest_asyncio.fixture
async def test_server_block_page1(unused_tcp_port: int) -> AsyncIterator[str]:
    app = web.Application()

    async def handle_root(_):
        return web.Response(text='<a href="/page1">Page1</a>', content_type="text/html")

    async def handle_page1(_):
        return web.Response(text="<html><body>Page1</body></html>", content_type="text/html")

    async def handle_robots(_):
        return web.Response(
            text="User-agent: TestAgent/1.0\nDisallow: /page1", content_type="text/plain"
        )

    app.router.add_get("/", handle_root)
    app.router.add_get("/page1", handle_page1)
    app.router.add_get("/robots.txt", handle_robots)

    async for url in _serve_app(app, unused_tcp_port):
        yield url


@pytest_asyncio.fixture
async def test_server_large(unused_tcp_port: int) -> AsyncIterator[str]:
    app = web.Application()
    links = "".join(f'<a href="/page{i}">Page{i}</a>' for i in range(1, STRESS_PAGES))

    async def handle_root(_):
        return web.Response(text=links, content_type="text/html")

    async def handle_page(_):
        return web.Response(text="<h1>Page</h1>", content_type="text/html")

    async def handle_robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", handle_root)
    app.router.add_get("/robots.txt", handle_robots)
    for i in range(1, STRESS_PAGES):
        app.router.add_get(f"/page{i}", handle_page)

    async for url in _serve_app(app, unused_tcp_port):
        yield url


# --------------------------------------------------------------------------- #
#                                   Tests                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio()
async def test_basic_crawl(empty_wordlists, test_server_allow_all: str):
    config = ScannerConfig(
        base_url=test_server_allow_all,
        max_depth=3,
        timeout=2.0,
        user_agent="TestAgent/1.0",
        rate_limit=10.0,
        wordlists=empty_wordlists,
    )
    pages = await run_crawler(config)
    urls = {normalize_url(p.url) for p in pages}

    assert normalize_url(test_server_allow_all) in urls
    assert normalize_url(f"{test_server_allow_all}/page1") in urls
    assert normalize_url(f"{test_server_allow_all}/page2") in urls
    assert normalize_url(f"{test_server_allow_all}/page3") not in urls
    assert len(urls) == 3


@pytest.mark.asyncio()
async def test_timeout_on_deep_page(empty_wordlists, test_server_allow_all: str):
    config = ScannerConfig(
        base_url=test_server_allow_all,
        max_depth=3,
        timeout=1.0,
        user_agent="TestAgent/1.0",
        rate_limit=10.0,
        wordlists=empty_wordlists,
    )
    pages = await run_crawler(config)
    urls = {normalize_url(p.url) for p in pages}

    assert normalize_url(test_server_allow_all) in urls
    assert normalize_url(f"{test_server_allow_all}/page1") in urls
    assert normalize_url(f"{test_server_allow_all}/page2") in urls
    assert normalize_url(f"{test_server_allow_all}/page3") not in urls
    assert len(urls) == 3


@pytest.mark.asyncio()
async def test_respect_robots(empty_wordlists, test_server_block_page1: str):
    config = ScannerConfig(
        base_url=test_server_block_page1,
        max_depth=1,
        timeout=1.0,
        user_agent="TestAgent/1.0",
        rate_limit=10.0,
        wordlists=empty_wordlists,
    )
    pages = await run_crawler(config)
    urls = {normalize_url(p.url) for p in pages}

    assert normalize_url(test_server_block_page1) in urls
    assert normalize_url(f"{test_server_block_page1}/page1") not in urls


@pytest.mark.asyncio()
async def test_depth_limit(empty_wordlists, test_server_block_page1: str):
    config = ScannerConfig(
        base_url=test_server_block_page1,
        max_depth=0,
        timeout=1.0,
        user_agent="TestAgent/1.0",
        rate_limit=10.0,
        wordlists=empty_wordlists,
    )
    pages = await run_crawler(config)
    assert {normalize_url(p.url) for p in pages} == {normalize_url(test_server_block_page1)}


@pytest.mark.asyncio()
@pytest.mark.slow()
async def test_stress_crawl(empty_wordlists, test_server_large: str):
    config = ScannerConfig(
        base_url=test_server_large,
        max_depth=1,
        timeout=2.0,
        user_agent="TestAgent/1.0",
        rate_limit=500.0,
        wordlists=empty_wordlists,
    )
    pages = await run_crawler(config, expected_pages=STRESS_PAGES)
    urls = {normalize_url(p.url) for p in pages}

    assert len(urls) == STRESS_PAGES
    assert normalize_url(test_server_large) in urls
    for i in range(1, STRESS_PAGES):
        assert normalize_url(f"{test_server_large}/page{i}") in urls


@pytest.mark.asyncio()
async def test_crawler_handles_404(empty_wordlists, unused_tcp_port: int):
    app = web.Application()

    async def handle_root(_):
        return web.Response(text='<a href="/missing">Broken Link</a>', content_type="text/html")

    async def handle_robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", handle_root)
    app.router.add_get("/robots.txt", handle_robots)

    async for base in _serve_app(app, unused_tcp_port):
        config = ScannerConfig(
            base_url=base,
            max_depth=1,
            timeout=2.0,
            user_agent="TestAgent/1.0",
            rate_limit=10.0,
            wordlists=empty_wordlists,
        )
        pages = await run_crawler(config)

    urls = {normalize_url(p.url) for p in pages}
    assert normalize_url(base) in urls
    assert normalize_url(f"{base}/missing") not in urls


@pytest.mark.asyncio()
async def test_concurrency(empty_wordlists, unused_tcp_port: int):
    """Ensure that two slow pages are fetched concurrently."""
    app = web.Application()

    async def slow1(_):
        await asyncio.sleep(SLOW_SLEEP)
        return web.Response(text="<h1>Slow1</h1>", content_type="text/html")

    async def slow2(_):
        await asyncio.sleep(SLOW_SLEEP)
        return web.Response(text="<h1>Slow2</h1>", content_type="text/html")

    async def root(_):
        return web.Response(
            text='<a href="/slow1">S1</a><a href="/slow2">S2</a>',
            content_type="text/html",
        )

    async def robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", root)
    app.router.add_get("/slow1", slow1)
    app.router.add_get("/slow2", slow2)
    app.router.add_get("/robots.txt", robots)

    async for base in _serve_app(app, unused_tcp_port):
        config = ScannerConfig(
            base_url=base,
            max_depth=1,
            timeout=5.0,
            user_agent="TestAgent/1.0",
            rate_limit=2.0,
            wordlists=empty_wordlists,
        )
        start = time.perf_counter()
        pages = await run_crawler(config, expected_pages=3)
        elapsed = time.perf_counter() - start

    assert elapsed < SLOW_SLEEP * 1.5
    urls = {normalize_url(p.url) for p in pages}
    assert normalize_url(f"{base}/slow1") in urls
    assert normalize_url(f"{base}/slow2") in urls


@pytest.mark.asyncio()
async def test_retry_on_server_error(empty_wordlists, unused_tcp_port: int):
    app = web.Application()
    call_count = {"n": 0}

    async def flaky(_):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return web.Response(status=500)
        return web.Response(text="<h1>Recover</h1>", content_type="text/html")

    async def root(_):
        return web.Response(
            text='<a href="/flaky">Flaky</a>',
            content_type="text/html",
        )

    async def robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", root)
    app.router.add_get("/flaky", flaky)
    app.router.add_get("/robots.txt", robots)

    async for base in _serve_app(app, unused_tcp_port):
        config = ScannerConfig(
            base_url=base,
            max_depth=1,
            timeout=5.0,
            user_agent="TestAgent/1.0",
            rate_limit=5.0,
            wordlists=empty_wordlists,
            retry_times=3,
        )
        pages = await run_crawler(config, expected_pages=2)

    urls = {normalize_url(p.url) for p in pages}
    assert normalize_url(f"{base}/flaky") in urls
    assert call_count["n"] == 3
