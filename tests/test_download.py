"""
Testes de /download (rota refatorada + VideoDownloader service).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from anm_db.api.main import app
from anm_db.api.deps import get_db


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_anime_by_slug = AsyncMock(return_value={
        "id": 1,
        "slug": "one-piece",
        "titulo": "One Piece",
    })
    return db


@pytest.fixture
def client(mock_db):
    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _mock_episode(**overrides):
    defaults = {
        "id": 1,
        "anime_id": 1,
        "numero": 1,
        "titulo": "Ep 1",
        "titulo_pt": None,
        "url_cdn": "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8",
        "url_af": "https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q",
        "fonte_ativa": "cdn",
    }
    defaults.update(overrides)
    return defaults


def _patch_resolve(result_url="https://example.com/video.mp4", source="cdn"):
    """Patcha VideoDownloader.resolve para retornar um DownloadResult mockado."""
    from anm_db.services.downloader import DownloadResult
    return patch(
        "anm_db.api.routes.download.VideoDownloader.resolve",
        AsyncMock(return_value=DownloadResult(
            url=result_url,
            content_type="video/mp4",
            filename="one-piece-ep1.mp4",
            source_used=source,
            transcoded=False,
        )),
    )


def _patch_stream(chunks=(b"chunk1", b"chunk2")):
    async def _gen():
        for c in chunks:
            yield c
    return patch(
        "anm_db.api.routes.download.VideoDownloader.stream",
        side_effect=lambda *a, **kw: _gen(),
    )


def test_download_anime_not_found(client, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value=None)
    resp = client.get("/download/nonexistent/1")
    assert resp.status_code == 404


def test_download_no_source_available(client, mock_db):
    with patch(
        "anm_db.api.routes.download.VideoDownloader.resolve",
        AsyncMock(return_value=None),
    ):
        resp = client.get("/download/one-piece/1")
    assert resp.status_code == 502
    assert "No video source" in resp.json()["detail"]


def test_download_invalid_source_param(client, mock_db):
    resp = client.get("/download/one-piece/1?source=invalid")
    assert resp.status_code == 422


def test_download_invalid_format_param(client, mock_db):
    resp = client.get("/download/one-piece/1?format=avi")
    assert resp.status_code == 422


def test_download_mp4_success(client, mock_db):
    with _patch_resolve() as p_resolve, _patch_stream() as p_stream:
        resp = client.get("/download/one-piece/1?format=mp4")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")
    assert "one-piece-ep1.mp4" in resp.headers["content-disposition"]
    assert resp.headers["x-source"] == "cdn"


def test_download_hls_format(client, mock_db):
    with _patch_resolve() as p_resolve, _patch_stream() as p_stream:
        resp = client.get("/download/one-piece/1?format=hls")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-mpegurl")
    assert "one-piece-ep1.m3u8" in resp.headers["content-disposition"]


def test_download_ts_format(client, mock_db):
    with _patch_resolve() as p_resolve, _patch_stream() as p_stream:
        resp = client.get("/download/one-piece/1?format=ts")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp2t")
    assert "one-piece-ep1.ts" in resp.headers["content-disposition"]


def test_download_af_source(client, mock_db):
    with _patch_resolve(
        result_url="https://bp.blogspot.com/abc/playback.mp4",
        source="af",
    ), _patch_stream():
        resp = client.get("/download/one-piece/1?source=af")
    assert resp.status_code == 200
    assert resp.headers["x-source"] == "af"
