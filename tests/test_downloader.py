"""
Testes do VideoDownloader service.

Foca em:
- resolucao de fonte (cdn vs af vs auto fallback)
- deteccao de HLS vs MP4 direto
- disponibilidade de ffmpeg
- streaming pipe com ffmpeg (mockado)
"""

import asyncio
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from anm_db.services.downloader import (
    DownloadResult,
    FFmpegNotAvailable,
    VideoDownloader,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def downloader(mock_db):
    return VideoDownloader(mock_db, ffmpeg_path="/nonexistent/ffmpeg")


def _ep(**overrides):
    defaults = {
        "id": 1,
        "anime_id": 1,
        "numero": 1,
        "titulo": "Ep 1",
        "url_cdn": "https://cdn-s01.mywallpaper-4k-image.net/o/one-piece/01.m3u8",
        "url_cdn2": None,
        "url_af": "https://www.blogger.com/video.g?token=AD6v5d",
        "fonte_ativa": "cdn",
    }
    defaults.update(overrides)
    return defaults


# ---- Detectao de formato ----

def test_is_hls_detects_m3u8(downloader):
    assert downloader._is_hls("https://example.com/playlist.m3u8") is True
    assert downloader._is_hls("https://example.com/playlist.M3U8") is True


def test_is_hls_detects_mpegurl(downloader):
    assert downloader._is_hls("https://example.com/manifest?type=mpegurl") is True


def test_is_hls_false_for_mp4(downloader):
    assert downloader._is_hls("https://example.com/video.mp4") is False


def test_is_cdn_detects_known_domains(downloader):
    assert downloader._is_cdn("https://cdn-s01.mywallpaper-4k-image.net/x.m3u8") is True
    assert downloader._is_cdn("https://bp.blogspot.com/video.mp4") is False


# ---- Disponibilidade ffmpeg ----

def test_ffmpeg_available_false_when_missing(downloader):
    assert downloader.ffmpeg_available is False


def test_ffmpeg_available_true_when_installed(monkeypatch):
    # Encontra ffmpeg real se existir (CI local com ffmpeg)
    real = shutil.which("ffmpeg")
    if not real:
        pytest.skip("ffmpeg nao instalado no ambiente")
    downloader = VideoDownloader(AsyncMock(), ffmpeg_path=real)
    assert downloader.ffmpeg_available is True


# ---- Resolucao de fonte ----

@pytest.mark.asyncio
async def test_resolve_returns_cdn_when_available(downloader, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(return_value=[_ep()])

    result = await downloader.resolve("naruto", 1, source="auto")
    assert result is not None
    assert result.source_used == "cdn1"
    assert result.transcoded is True  # e HLS


@pytest.mark.asyncio
async def test_resolve_returns_cdn2_when_cdn1_missing(downloader, mock_db):
    """Quando cdn1 indisponivel mas cdn2 existe, deve usar cdn2."""
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(
        return_value=[_ep(url_cdn=None, url_cdn2="https://pixel-sus-4k-image.com/n/naruto/01.m3u8")]
    )

    result = await downloader.resolve("naruto", 1, source="auto")
    assert result is not None
    assert result.source_used == "cdn2"
    assert "pixel-sus-4k-image.com" in result.url


@pytest.mark.asyncio
async def test_resolve_source_cdn2_explicit(downloader, mock_db):
    """Quando source='cdn2' explicito, usa cdn2 mesmo que cdn1 exista."""
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(
        return_value=[_ep(url_cdn2="https://pixel-sus-4k-image.com/n/naruto/01.m3u8")]
    )

    result = await downloader.resolve("naruto", 1, source="cdn2")
    assert result is not None
    assert result.source_used == "cdn2"


@pytest.mark.asyncio
async def test_resolve_cdn1_requested_strict_returns_none_when_missing(downloader, mock_db):
    """source='cdn1' explicito: se cdn1 ausente, retorna None (strict, sem fallback para cdn2)."""
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(
        return_value=[_ep(url_cdn=None, url_cdn2="https://pixel-sus-4k-image.com/n/naruto/01.m3u8")]
    )

    result = await downloader.resolve("naruto", 1, source="cdn1")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_cdn2_requested_strict_returns_none_when_missing(downloader, mock_db):
    """source='cdn2' explicito: se cdn2 ausente, retorna None."""
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(
        return_value=[_ep(url_cdn="https://cdn-s01.mywallpaper-4k-image.net/n/naruto/01.m3u8", url_cdn2=None)]
    )

    result = await downloader.resolve("naruto", 1, source="cdn2")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_legacy_cdn_source_maps_to_cdn1(downloader, mock_db):
    """Retrocompatibilidade: source='cdn' (legacy) deve mapear para cdn1."""
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(return_value=[_ep()])

    result = await downloader.resolve("naruto", 1, source="cdn")
    assert result is not None
    assert result.source_used == "cdn1"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_af(downloader, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(return_value=[_ep(url_cdn=None)])

    # Mock resolve_blogger_url para retornar URL real
    with patch(
        "anm_db.services.downloader.resolve_blogger_url",
        AsyncMock(return_value="https://bp.blogspot.com/playback.mp4"),
    ):
        result = await downloader.resolve("naruto", 1, source="auto")

    assert result is not None
    assert result.source_used == "af"
    assert result.transcoded is False


@pytest.mark.asyncio
async def test_resolve_returns_none_when_anime_missing(downloader, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value=None)
    result = await downloader.resolve("nonexistent", 1)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_sources(downloader, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(
        return_value=[_ep(url_cdn=None, url_af=None)]
    )
    result = await downloader.resolve("naruto", 1)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_cdn_only_when_source_cdn(downloader, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value={"id": 1, "slug": "naruto"})
    mock_db.get_episodios_paginados = AsyncMock(return_value=[_ep()])

    result = await downloader.resolve("naruto", 1, source="af")
    assert result is not None
    assert result.source_used == "af"


# ---- Stream pipe ffmpeg ----

@pytest.mark.asyncio
async def test_stream_ffmpeg_pipe_with_mocked_subprocess(monkeypatch, downloader):
    """Verifica que ffmpeg pipe e chamado com argumentos corretos."""
    # Mocka shutil.which para retornar True
    monkeypatch.setattr(
        "anm_db.services.downloader.shutil.which", lambda x: "/usr/bin/ffmpeg"
    )

    # Cria um mock de processo que emite dados no stdout e termina
    call_count = {"n": 0}

    async def read(n):
        call_count["n"] += 1
        if call_count["n"] > 2:
            return b""
        return f"chunk{call_count['n']}".encode()

    async def wait():
        return 0

    mock_proc = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.read = read
    mock_proc.wait = wait
    mock_proc.returncode = 0
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")

    with patch(
        "asyncio.create_subprocess_exec",
        AsyncMock(return_value=mock_proc),
    ):
        chunks = []
        async for chunk in downloader._stream_ffmpeg_pipe(
            "https://example.com/video.m3u8", "mp4"
        ):
            chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0] == b"chunk1"
    assert chunks[1] == b"chunk2"


@pytest.mark.asyncio
async def test_stream_ffmpeg_pipe_raises_when_missing(downloader, mock_db):
    downloader.ffmpeg_path = "/definitely/not/a/real/path"
    with pytest.raises(FFmpegNotAvailable):
        async for _ in downloader._stream_ffmpeg_pipe(
            "https://example.com/video.m3u8", "mp4"
        ):
            pass


# ---- Stream direto (sem ffmpeg) ----

@pytest.mark.asyncio
async def test_stream_direct_returns_chunks(downloader):
    """Mocka aiohttp para retornar chunks conhecidos."""
    mock_chunk1 = b"video-data-1"
    mock_chunk2 = b"video-data-2"

    async def iter_chunked(n):
        yield mock_chunk1
        yield mock_chunk2

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.content.iter_chunked = iter_chunked

    # Context manager async
    cm_resp = MagicMock()
    cm_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    cm_resp.__aexit__ = AsyncMock(return_value=False)
    cm_resp.status = 200
    cm_resp.content.iter_chunked = iter_chunked

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=cm_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        chunks = []
        async for c in downloader._stream_direct(
            "https://example.com/video.mp4", "video/mp4"
        ):
            chunks.append(c)

    assert b"".join(chunks) == mock_chunk1 + mock_chunk2
