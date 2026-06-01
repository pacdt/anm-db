import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


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
    from api.main import app
    from api.deps import get_db

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
        "url_cdn": "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8",
        "url_af": "https://www.blogger.com/video.g?token=AD6v5dxpzTTm3WV3Q",
        "fonte_ativa": "cdn",
    }
    defaults.update(overrides)
    return defaults


def test_download_auto_cdn(client, mock_db):
    mock_db.get_episodios_paginados = AsyncMock(return_value=[_mock_episode()])

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.content = AsyncMock()
    mock_resp.content.iter_chunked = MagicMock(return_value=iter([b"video-data"]))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("api.routes.download.aiohttp.ClientSession", return_value=mock_session):
        resp = client.get("/download/one-piece/1?source=cdn")

    assert resp.status_code == 200


def test_download_anime_not_found(client, mock_db):
    mock_db.get_anime_by_slug = AsyncMock(return_value=None)
    resp = client.get("/download/nonexistent/1")
    assert resp.status_code == 404


def test_download_episode_not_found(client, mock_db):
    mock_db.get_episodios_paginados = AsyncMock(return_value=[])
    resp = client.get("/download/one-piece/99999")
    assert resp.status_code == 404


def test_download_no_source_available(client, mock_db):
    mock_db.get_episodios_paginados = AsyncMock(
        return_value=[_mock_episode(url_cdn=None, url_af=None)]
    )
    resp = client.get("/download/one-piece/1")
    assert resp.status_code == 502
    assert "No video source available" in resp.json()["detail"]


def test_download_invalid_source_param(client, mock_db):
    resp = client.get("/download/one-piece/1?source=invalid")
    assert resp.status_code == 422
