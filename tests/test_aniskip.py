import pytest
from aniskip import fetch_skip_times


@pytest.mark.asyncio
async def test_fetch_skip_times_nonexistent():
    import aiohttp
    session = aiohttp.ClientSession()
    try:
        result = await fetch_skip_times(99999999, 1, session)
        assert result == {}
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_fetch_skip_times_handles_errors():
    import aiohttp
    session = aiohttp.ClientSession()
    try:
        result = await fetch_skip_times(0, 0, session)
        assert isinstance(result, dict)
    finally:
        await session.close()
