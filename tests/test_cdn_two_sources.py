"""Testes para cdn.py e cdn_checker cobrindo 2 fontes CDN."""
import re
import pytest
import aiohttp
from aioresponses import aioresponses

from cdn_checker import (
    CDN_DOMAINS,
    build_url,
    check_all_cdn_episodes,
    check_cdn_episode,
    format_ep,
)


def test_cdn_domains_has_both():
    """Garante que as 2 CDNs estao configuradas."""
    assert "cdn-s01.mywallpaper-4k-image.net" in CDN_DOMAINS
    assert "pixel-sus-4k-image.com" in CDN_DOMAINS
    assert len(CDN_DOMAINS) == 2


def test_format_ep():
    assert format_ep(1) == "01"
    assert format_ep(10) == "10"
    assert format_ep(99) == "99"
    assert format_ep(100) == "100"


def test_build_url_cdn1():
    url = build_url("cdn-s01.mywallpaper-4k-image.net", "one-piece", 5)
    assert url == "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/05.mp4/index.m3u8"


def test_build_url_cdn2():
    url = build_url("pixel-sus-4k-image.com", "naruto", 1)
    assert url == "https://pixel-sus-4k-image.com/stream/n/naruto/01.mp4/index.m3u8"


def test_build_url_slug_first_char():
    url = build_url("example.com", "another", 1)
    assert "/stream/a/another/" in url
    url = build_url("example.com", "zombie-land", 1)
    assert "/stream/z/zombie-land/" in url


@pytest.mark.asyncio
async def test_check_cdn_episode_both_404_returns_none():
    with aioresponses() as m:
        m.head(re.compile(r"https://cdn-s01\.mywallpaper-4k-image\.net/.*"), status=404)
        m.head(re.compile(r"https://pixel-sus-4k-image\.com/.*"), status=404)
        async with aiohttp.ClientSession() as session:
            result = await check_cdn_episode("nonexistent", 1, session)
            assert result is None


@pytest.mark.asyncio
async def test_check_cdn_episode_legacy_returns_first_hit():
    """check_cdn_episode (legacy) deve retornar a primeira URL disponivel."""
    with aioresponses() as m:
        m.head(re.compile(r"https://cdn-s01\.mywallpaper-4k-image\.net/.*"), status=200)
        m.head(re.compile(r"https://pixel-sus-4k-image\.com/.*"), status=200)
        async with aiohttp.ClientSession() as session:
            result = await check_cdn_episode("one-piece", 1, session)
            assert result is not None
            assert "cdn-s01.mywallpaper-4k-image.net" in result


@pytest.mark.asyncio
async def test_check_all_cdn_episodes_both_returned():
    """Quando ambas CDNs respondem 200, retorna dict com 2 entradas."""
    with aioresponses() as m:
        m.head(re.compile(r"https://cdn-s01\.mywallpaper-4k-image\.net/.*"), status=200)
        m.head(re.compile(r"https://pixel-sus-4k-image\.com/.*"), status=200)
        async with aiohttp.ClientSession() as session:
            sources = await check_all_cdn_episodes("one-piece", 1, session)
            assert len(sources) == 2
            assert "cdn-s01.mywallpaper-4k-image.net" in sources
            assert "pixel-sus-4k-image.com" in sources


@pytest.mark.asyncio
async def test_check_all_cdn_episodes_only_cdn2():
    """Quando cdn1 falha e cdn2 funciona, retorna so cdn2."""
    with aioresponses() as m:
        m.head(re.compile(r"https://cdn-s01\.mywallpaper-4k-image\.net/.*"), status=404)
        m.head(re.compile(r"https://pixel-sus-4k-image\.com/.*"), status=200)
        async with aiohttp.ClientSession() as session:
            sources = await check_all_cdn_episodes("anime", 1, session)
            assert len(sources) == 1
            assert "pixel-sus-4k-image.com" in sources
            assert "cdn-s01.mywallpaper-4k-image.net" not in sources


@pytest.mark.asyncio
async def test_check_all_cdn_episodes_neither():
    """Quando nenhuma CDN funciona, retorna dict vazio."""
    with aioresponses() as m:
        m.head(re.compile(r"https://cdn-s01\.mywallpaper-4k-image\.net/.*"), status=404)
        m.head(re.compile(r"https://pixel-sus-4k-image\.com/.*"), status=404)
        async with aiohttp.ClientSession() as session:
            sources = await check_all_cdn_episodes("anime", 1, session)
            assert sources == {}


@pytest.mark.asyncio
async def test_check_all_cdn_episodes_handles_timeouts():
    """Timeouts sao tratados e CDN disponivel ainda e retornada."""
    import asyncio
    with aioresponses() as m:
        m.head(re.compile(r"https://cdn-s01\.mywallpaper-4k-image\.net/.*"), exception=asyncio.TimeoutError())
        m.head(re.compile(r"https://pixel-sus-4k-image\.com/.*"), status=200)
        async with aiohttp.ClientSession() as session:
            sources = await check_all_cdn_episodes("anime", 1, session)
            assert len(sources) == 1
            assert "pixel-sus-4k-image.com" in sources
