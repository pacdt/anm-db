import pytest
import aiohttp
from cdn_checker import build_url, format_ep, check_cdn_episode


def test_format_ep():
    assert format_ep(1) == "01"
    assert format_ep(10) == "10"
    assert format_ep(99) == "99"
    assert format_ep(100) == "100"


def test_build_url():
    url = build_url("cdn-s01.mywallpaper-4k-image.net", "one-piece", 5)
    assert url == "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/05.mp4/index.m3u8"

    url = build_url("pixel-sus-4k-image.com", "naruto", 1)
    assert url == "https://pixel-sus-4k-image.com/stream/n/naruto/01.mp4/index.m3u8"


def test_build_url_slug_first_char():
    url = build_url("example.com", "another", 1)
    assert "/stream/a/another/" in url

    url = build_url("example.com", "zombie-land", 1)
    assert "/stream/z/zombie-land/" in url


@pytest.mark.asyncio
async def test_check_cdn_returns_none_for_nonexistent():
    session = aiohttp.ClientSession()
    try:
        result = await check_cdn_episode("nonexistent-anime-12345", 1, session)
        assert result is None
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_check_cdn_handles_connection_errors():
    session = aiohttp.ClientSession()
    try:
        result = await check_cdn_episode("test-anime", 99999, session)
        assert result is None
    finally:
        await session.close()
