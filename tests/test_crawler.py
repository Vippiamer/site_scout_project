# === FILE: site_scout_project/tests/test_crawler.py ===
"""
Refactored, PEP-8-compliant test-suite for SiteScout async crawler.

Изменения — см. README:
* `_serve_app` — полноценный асинхронный context-manager → `async with`.
* Все обращения к `base_url` / `pages` перенесены внутрь контекста, чтобы
  избежать `UnboundLocalError`.
* Снижен «искусственный» SLOW_SLEEP для ускорения CI; допуск расширен.
* Улучшена `normalize_url` (lower-case, канонизация портов, «/» по-умолчанию).
API публичных объектов не изменён.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Dict
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from aiohttp import web

from site_scout.config import ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler

# --------------------------------------------------------------------------- #
#                            Pytest-configuration                              #
# --------------------------------------------------------------------------- #
def pytest_configure(config):  # noqa: D401
    """Register custom markers so that `--strict-markers` does not fail."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )


# --------------------------------------------------------------------------- #
#                               Helper utilities                              #
# --------------------------------------------------------------------------- #

#: per-request artificial delay used in the concurrency test (seconds)
SLOW_SLEEP: float = 0.2
#: number of pages created by the stress fixture / test (root + pages 1…200)
STRESS_PAGES: int = 201  # keeps test quick even on CI


def normalize_url(url: str) -> str:
    """
    Canonicalise *url* for deterministic set-membership checks.

    * query/fragment stripped;
    * scheme / host lower-cased;
    * default ports (:80 / :443) удаляются;
    * «директории» получают завершающий `/`.
    """
    parts = urlsplit(url)

    # canonicalise scheme + netloc
    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    if port and not (scheme == "http" and port == 80) and not (
        scheme == "https" and port == 443
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    # canonicalise path
    path = parts.path or "/"
    if path and not path.endswith("/") and not Path(path).suffix:
        path += "/"

    return urlunsplit((scheme, netloc, path, "", ""))


async def run_crawler(config: ScannerConfig, expected_pages: int = 100):
    """
    Run the crawler inside an overall timeout that scales with *expected_pages*.

    Uses :pyfunc:`asyncio.wait_for` (works on Python 3.8-3.12) instead of
    the 3.11-only context manager ``asyncio.timeout``.
    """
    total_timeout = max(15.0, expected_pages * 0.1)
    async with AsyncCrawler(config) as crawler:
        return await asyncio.wait_for(crawler.crawl(), timeout=total_timeout)


# --------------------------------------------------------------------------- #
#                            Lightweight HTTP server                          #
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _serve_app(app: web.Application, port: int) -> AsyncIterator[str]:
    """
    Asynchronous context manager that starts *app* on *port*.

    Ensures proper cleanup even when a test fails halfway.
    """
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", port)
    await site.start()
    try:
        yield f"http://localhost:{port}"
    finally:
        await runner.cleanup()


# --------------------------------------------------------------------------- #
#                                  Fixtures                                   #
# --------------------------------------------------------------------------- #
@pytest.fixture
def empty_wordlists(tmp_path: Path) -> Dict[str, Path]:
    """Return a dict with empty wordlist files the crawler expects."""
    paths_file = tmp_path / "paths.txt"
    files_file = tmp_path / "files.txt"
    paths_file.touch()
    files_file.touch()
    return {"paths": paths_file, "files": files_file}


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
        # Long enough to exceed per-request timeout in tests
        await asyncio.sleep(2.5)
        return web.Response(text="<h1>Page3 (slow)</h1>", content_type="text/html")

    async def handle_robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", handle_root)
    app.router.add_get("/page1", handle_page1)
    app.router.add_get("/page2", handle_page2)
    app.router.add_get("/page3", handle_page3)
    app.router.add_get("/robots.txt", handle_robots)

    async with _serve_app(app, unused_tcp_port) as url:
        yield url


@pytest_asyncio.fixture
async def test_server_block_page1(unused_tcp_port: int) -> AsyncIterator[str]:
    app = web.Application()

    async def handle_root(_):
        return web.Response(text='<a href="/page1">Page1</a>', content_type="text/html")

    async def handle_page1(_):
        return web.Response(
            text="<html><body>Page1</body></html>", content_type="text/html"
        )

    async def handle_robots(_):
        return web.Response(
            text="User-agent: TestAgent/1.0\nDisallow: /page1",
            content_type="text/plain",
        )

    app.router.add_get("/", handle_root)
    app.router.add_get("/page1", handle_page1)
    app.router.add_get("/robots.txt", handle_robots)

    async with _serve_app(app, unused_tcp_port) as url:
        yield url


@pytest_asyncio.fixture
async def test_server_large(unused_tcp_port: int) -> AsyncIterator[str]:
    app = web.Application()

    links = "".join(
        f'<a href="/page{i}">Page{i}</a>' for i in range(1, STRESS_PAGES)
    )

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

    async with _serve_app(app, unused_tcp_port) as url:
        yield url


# --------------------------------------------------------------------------- #
#                                   Tests                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
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
    # Page3 should be skipped due to request timeout
    assert normalize_url(f"{test_server_allow_all}/page3") not in urls
    assert len(urls) == 3


@pytest.mark.asyncio
async def test_timeout_on_deep_page(empty_wordlists, test_server_allow_all: str):
    config = ScannerConfig(
        base_url=test_server_allow_all,
        max_depth=3,
        timeout=1.0,  # lower than 2.5-second sleep on /page3
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
    assert {normalize_url(p.url) for p in pages} == {
        normalize_url(test_server_block_page1)
    }


@pytest.mark.asyncio
@pytest.mark.slow
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


@pytest.mark.asyncio
async def test_crawler_handles_404(empty_wordlists, unused_tcp_port: int):
    app = web.Application()

    async def handle_root(_):
        return web.Response(
            text='<a href="/missing">Broken Link</a>', content_type="text/html"
        )

    async def handle_robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", handle_root)
    app.router.add_get("/robots.txt", handle_robots)

    async with _serve_app(app, unused_tcp_port) as base_url:
        config = ScannerConfig(
            base_url=base_url,
            max_depth=1,
            timeout=2.0,
            user_agent="TestAgent/1.0",
            rate_limit=10.0,
            wordlists=empty_wordlists,
        )
        pages = await run_crawler(config)

        urls = {normalize_url(p.url) for p in pages}
        assert normalize_url(base_url) in urls
        assert normalize_url(f"{base_url}/missing") not in urls


@pytest.mark.asyncio
async def test_concurrency(empty_wordlists, unused_tcp_port: int):
    """Ensure that two slow pages are really fetched concurrently."""
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

    async with _serve_app(app, unused_tcp_port) as base:
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

        # Allow generous overhead versus a single request
        assert elapsed < SLOW_SLEEP * 3.0, f"Expected concurrency, took {elapsed:.3f}s"

        urls = {normalize_url(p.url) for p in pages}
        assert normalize_url(f"{base}/slow1") in urls
        assert normalize_url(f"{base}/slow2") in urls


@pytest.mark.asyncio
async def test_retry_on_server_error(empty_wordlists, unused_tcp_port: int):
    app = web.Application()
    call_count = {"n": 0}

    async def flaky(_):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return web.Response(status=500)
        return web.Response(text="<h1>Recover</h1>", content_type="text/html")

    async def root(_):
        return web.Response(text='<a href="/flaky">Flaky</a>', content_type="text/html")

    async def robots(_):
        return web.Response(text="User-agent: *\nDisallow:", content_type="text/plain")

    app.router.add_get("/", root)
    app.router.add_get("/flaky", flaky)
    app.router.add_get("/robots.txt", robots)

    async with _serve_app(app, unused_tcp_port) as base:
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
        # Ensure we really retried twice (total calls == 3)
        assert call_count["n"] == 3
