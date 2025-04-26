# tests/test_crawler.py
import sys
import pathlib
# Ensure project root containing site_scout package is in Python path
def _add_project_to_path():
    project_root = pathlib.Path().resolve()
    while True:
        if (project_root / "site_scout").is_dir():
            sys.path.insert(0, str(project_root))
            return
        if project_root.parent == project_root:
            return
        project_root = project_root.parent
_add_project_to_path()

import asyncio
import pytest
import pytest_asyncio
from aiohttp import web
from pathlib import Path

from site_scout.config import ScannerConfig
from site_scout.crawler.crawler import AsyncCrawler

@pytest_asyncio.fixture
async def test_server(unused_tcp_port):
    app = web.Application()

    async def handle_root(request):
        return web.Response(text='<a href="/page1">Page1</a>', content_type='text/html')

    async def handle_page1(request):
        return web.Response(text='<html><body>Page1</body></html>', content_type='text/html')

    async def handle_robots(request):
        # Корректно оформленный строковый литерал с переносом строки
        robots_text = "User-agent: TestAgent/1.0\nDisallow: /page1"
        return web.Response(text=robots_text, content_type='text/plain')

    async def handle_slow(request):
        await asyncio.sleep(2)
        return web.Response(text='slow', content_type='text/plain')

    app.router.add_get('/', handle_root)
    app.router.add_get('/page1', handle_page1)
    app.router.add_get('/robots.txt', handle_robots)
    app.router.add_get('/slow', handle_slow)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', unused_tcp_port)
    await site.start()
    yield f"http://localhost:{unused_tcp_port}"
    await runner.cleanup()

@pytest.mark.asyncio
async def test_basic_crawl(tmp_path: Path, test_server):
    paths_file = tmp_path / 'paths.txt'
    files_file = tmp_path / 'files.txt'
    paths_file.write_text('', encoding='utf-8')
    files_file.write_text('', encoding='utf-8')

    config = ScannerConfig(
        base_url=test_server,
        max_depth=1,
        timeout=1.0,
        user_agent='TestAgent/1.0',
        rate_limit=10.0,
        wordlists={'paths': paths_file, 'files': files_file},
    )
    crawler = AsyncCrawler(config)
    pages = await crawler.crawl()
    urls = {page.url for page in pages}

    assert test_server in urls
    assert f"{test_server}/page1" in urls
    assert len(urls) == 2

@pytest.mark.asyncio
async def test_respect_robots(tmp_path: Path, test_server):
    paths_file = tmp_path / 'paths.txt'
    files_file = tmp_path / 'files.txt'
    paths_file.write_text('', encoding='utf-8')
    files_file.write_text('', encoding='utf-8')

    config = ScannerConfig(
        base_url=test_server,
        max_depth=1,
        timeout=1.0,
        user_agent='TestAgent/1.0',
        rate_limit=10.0,
        wordlists={'paths': paths_file, 'files': files_file},
    )
    crawler = AsyncCrawler(config)
    pages = await crawler.crawl()
    urls = {page.url for page in pages}

    assert test_server in urls
    assert f"{test_server}/page1" not in urls

@pytest.mark.asyncio
async def test_depth_limit(tmp_path: Path, test_server):
    paths_file = tmp_path / 'paths.txt'
    files_file = tmp_path / 'files.txt'
    paths_file.write_text('', encoding='utf-8')
    files_file.write_text('', encoding='utf-8')

    config = ScannerConfig(
        base_url=test_server,
        max_depth=0,
        timeout=1.0,
        user_agent='TestAgent/1.0',
        rate_limit=10.0,
        wordlists={'paths': paths_file, 'files': files_file},
    )
    crawler = AsyncCrawler(config)
    pages = await crawler.crawl()

    assert [page.url for page in pages] == [test_server]

@pytest.mark.asyncio
async def test_timeout_handling(tmp_path: Path, test_server):
    paths_file = tmp_path / 'paths.txt'
    files_file = tmp_path / 'files.txt'
    paths_file.write_text('', encoding='utf-8')
    files_file.write_text('', encoding='utf-8')

    slow_url = f"{test_server}/slow"
    config = ScannerConfig(
        base_url=slow_url,
        max_depth=0,
        timeout=0.5,
        user_agent='TestAgent/1.0',
        rate_limit=10.0,
        wordlists={'paths': paths_file, 'files': files_file},
    )
    crawler = AsyncCrawler(config)
    pages = await crawler.crawl()
    assert pages == []
