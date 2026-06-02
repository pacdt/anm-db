import pytest
import re
import tempfile
import os
import asyncio
import aiohttp
from aioresponses import aioresponses
from db import DatabaseManager
from cdn_checker import check_cdn_episode
from aniskip import fetch_skip_times


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
async def db(db_path):
    database = DatabaseManager(db_path)
    await database.init_db()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_cdn_hit():
    with aioresponses() as m:
        m.head(
            "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8",
            status=200,
        )
        async with aiohttp.ClientSession() as session:
            result = await check_cdn_episode("one-piece", 1, session)
            assert result == "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8"


@pytest.mark.asyncio
async def test_cdn_miss():
    with aioresponses() as m:
        m.head(
            "https://cdn-s01.mywallpaper-4k-image.net/stream/n/nonexistent/01.mp4/index.m3u8",
            status=404,
        )
        async with aiohttp.ClientSession() as session:
            result = await check_cdn_episode("nonexistent", 1, session)
            assert result is None


@pytest.mark.asyncio
async def test_cdn_timeout_fallback():
    with aioresponses() as m:
        m.head(
            "https://cdn-s01.mywallpaper-4k-image.net/stream/t/test/01.mp4/index.m3u8",
            exception=asyncio.TimeoutError(),
        )
        async with aiohttp.ClientSession() as session:
            result = await check_cdn_episode("test", 1, session)
            assert result is None


@pytest.mark.asyncio
async def test_aniskip_hit():
    with aioresponses() as m:
        m.get(
            re.compile(r"https://api\.aniskip\.com/v2/skip-times/20/1.*"),
            payload={
                "found": True,
                "results": [
                    {
                        "skipType": "op",
                        "interval": {"startTime": 1.0, "endTime": 102.0},
                    }
                ],
            },
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_skip_times(20, 1, session=session)
            assert "op" in result
            assert result["op"]["start"] == 1.0
            assert result["op"]["end"] == 102.0


@pytest.mark.asyncio
async def test_aniskip_404():
    with aioresponses() as m:
        m.get(
            re.compile(r"https://api\.aniskip\.com/v2/skip-times/99999/1.*"),
            status=404,
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_skip_times(99999, 1, session=session)
            assert result == {}


@pytest.mark.asyncio
async def test_aniskip_timeout():
    with aioresponses() as m:
        m.get(
            re.compile(r"https://api\.aniskip\.com/v2/skip-times/20/1.*"),
            exception=asyncio.TimeoutError(),
        )
        async with aiohttp.ClientSession() as session:
            result = await fetch_skip_times(20, 1, session=session)
            assert result == {}


@pytest.mark.asyncio
async def test_db_upsert_skip_time(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
        "titulo": "Test Anime",
    })

    await db.upsert_skip_time(anime_id, 1, "op", 1.0, 102.0)
    await db.upsert_skip_time(anime_id, 1, "ed", 1200.0, 1300.0)

    skip_times = await db.get_skip_times(anime_id, 1)
    assert "op" in skip_times
    assert "ed" in skip_times
    assert skip_times["op"]["start"] == 1.0
    assert skip_times["ed"]["end"] == 1300.0


@pytest.mark.asyncio
async def test_db_skip_times_batch(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime-2",
        "tipo": "legendado",
        "titulo": "Test Anime 2",
    })

    await db.upsert_skip_time(anime_id, 1, "op", 1.0, 102.0)
    await db.upsert_skip_time(anime_id, 2, "op", 1.0, 95.0)
    await db.upsert_skip_time(anime_id, 2, "ed", 1200.0, 1300.0)

    batch = await db.get_skip_times_for_anime(anime_id)
    assert 1 in batch
    assert 2 in batch
    assert "op" in batch[1]
    assert "op" in batch[2]
    assert "ed" in batch[2]


@pytest.mark.asyncio
async def test_db_write_semaphore_concurrent(db):
    async def write_anime(i):
        return await db.upsert_anime({
            "slug": f"concurrent-{i}",
            "tipo": "legendado",
            "titulo": f"Concurrent {i}",
        })

    tasks = [write_anime(i) for i in range(5)]
    results = await asyncio.gather(*tasks)
    assert len(set(results)) == 5

    slugs = await db.list_all_slugs()
    assert len(slugs) >= 5
