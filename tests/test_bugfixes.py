"""Testes para correcoes de validacao e schema v3."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import DatabaseManager


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


# ---- DB: upsert_episodio com url_cdn2 ----

@pytest.mark.asyncio
async def test_upsert_episodio_with_url_cdn2(db):
    """Schema v3: url_cdn2 deve ser persistido."""
    anime_id = await db.upsert_anime({
        "slug": "naruto",
        "tipo": "legendado",
        "titulo": "Naruto",
    })

    await db.upsert_episodio(
        anime_id=anime_id,
        numero=1,
        url_cdn="https://cdn-s01.mywallpaper-4k-image.net/n/naruto/01.m3u8",
        url_cdn2="https://pixel-sus-4k-image.com/n/naruto/01.m3u8",
        url_af="https://www.blogger.com/video.g?token=ABC",
    )

    eps = await db.get_episodios_paginados("naruto", 1, 10)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["url_cdn"] == "https://cdn-s01.mywallpaper-4k-image.net/n/naruto/01.m3u8"
    assert ep["url_cdn2"] == "https://pixel-sus-4k-image.com/n/naruto/01.m3u8"
    assert ep["url_af"] == "https://www.blogger.com/video.g?token=ABC"


@pytest.mark.asyncio
async def test_upsert_episodio_three_sources_persisted(db):
    """Quando as 3 fontes estao disponiveis, todas devem ser salvas."""
    anime_id = await db.upsert_anime({
        "slug": "one-piece",
        "tipo": "legendado",
        "titulo": "One Piece",
    })

    await db.upsert_episodio(
        anime_id=anime_id,
        numero=1,
        url_cdn="https://cdn-s01.mywallpaper-4k-image.net/o/one-piece/01.m3u8",
        url_cdn2="https://pixel-sus-4k-image.com/o/one-piece/01.m3u8",
        url_af="https://www.blogger.com/video.g?token=DEF",
    )

    eps = await db.get_episodios_paginados("one-piece", 1, 10)
    assert all([eps[0]["url_cdn"], eps[0]["url_cdn2"], eps[0]["url_af"]])


@pytest.mark.asyncio
async def test_upsert_episodio_only_cdn1_and_af(db):
    """Quando cdn2 nao funciona, url_cdn2 fica None."""
    anime_id = await db.upsert_anime({
        "slug": "bleach",
        "tipo": "legendado",
        "titulo": "Bleach",
    })

    await db.upsert_episodio(
        anime_id=anime_id,
        numero=1,
        url_cdn="https://cdn-s01.mywallpaper-4k-image.net/b/bleach/01.m3u8",
        url_af="https://www.blogger.com/video.g?token=GHI",
    )

    eps = await db.get_episodios_paginados("bleach", 1, 10)
    assert eps[0]["url_cdn"] is not None
    assert eps[0]["url_cdn2"] is None
    assert eps[0]["url_af"] is not None


@pytest.mark.asyncio
async def test_upsert_episodio_only_af_fallback(db):
    """Quando nenhuma CDN funciona, so AF fica."""
    anime_id = await db.upsert_anime({
        "slug": "rare-anime",
        "tipo": "legendado",
        "titulo": "Rare",
    })

    await db.upsert_episodio(
        anime_id=anime_id,
        numero=1,
        url_af="https://www.blogger.com/video.g?token=JKL",
        fonte_ativa="animefire",
    )

    eps = await db.get_episodios_paginados("rare-anime", 1, 10)
    assert eps[0]["url_cdn"] is None
    assert eps[0]["url_cdn2"] is None
    assert eps[0]["url_af"] is not None


@pytest.mark.asyncio
async def test_upsert_episodio_update_preserves_missing_sources(db):
    """Update parcial: se primeira vez salvou 3 fontes e depois so uma, NAO sobrescreve."""
    anime_id = await db.upsert_anime({
        "slug": "anime-x",
        "tipo": "legendado",
        "titulo": "X",
    })

    await db.upsert_episodio(
        anime_id=anime_id,
        numero=1,
        url_cdn="https://cdn-s01.mywallpaper-4k-image.net/x/anime-x/01.m3u8",
        url_cdn2="https://pixel-sus-4k-image.com/x/anime-x/01.m3u8",
        url_af="https://www.blogger.com/video.g?token=MNO",
    )

    # Re-upsert com so url_af (COALESCE deve manter cdn1/cdn2)
    await db.upsert_episodio(
        anime_id=anime_id,
        numero=1,
        url_af="https://www.blogger.com/video.g?token=NEW",
    )

    eps = await db.get_episodios_paginados("anime-x", 1, 10)
    assert eps[0]["url_cdn"] is not None
    assert eps[0]["url_cdn2"] is not None
    assert eps[0]["url_af"] == "https://www.blogger.com/video.g?token=NEW"


# ---- DB: genero case-insensitive ----

@pytest.mark.asyncio
async def test_genero_lookup_case_insensitive_pt(db):
    """get_genero_by_nome_pt deve aceitar qualquer case."""
    await db.upsert_genero("Action", nome_pt="Ação")

    # Variantes de case
    assert (await db.get_genero_by_nome_pt("Ação")) is not None
    assert (await db.get_genero_by_nome_pt("ação")) is not None
    assert (await db.get_genero_by_nome_pt("AÇÃO")) is not None
    # Original em EN
    assert (await db.get_genero_by_nome_pt("action")) is not None
    assert (await db.get_genero_by_nome_pt("ACTION")) is not None


@pytest.mark.asyncio
async def test_genero_lookup_case_insensitive_en(db):
    """Se nao tem nome_pt, busca por nome (EN) tambem e case-insensitive."""
    await db.upsert_genero("Drama", nome_pt=None)

    assert (await db.get_genero_by_nome_pt("Drama")) is not None
    assert (await db.get_genero_by_nome_pt("drama")) is not None
    assert (await db.get_genero_by_nome_pt("DRAMA")) is not None


@pytest.mark.asyncio
async def test_genero_lookup_none_for_missing(db):
    assert (await db.get_genero_by_nome_pt("Inexistente")) is None


# ---- API: status validation ----

def test_api_status_invalid_returns_422():
    """status=invalid deve retornar 422 (validation error)."""
    from api.main import app
    client = TestClient(app)
    r = client.get("/animes?status=invalid")
    assert r.status_code == 422


def test_api_status_ongoing_accepted():
    from api.main import app
    client = TestClient(app)
    r = client.get("/animes?status=ongoing")
    assert r.status_code == 200


def test_api_status_finished_accepted():
    from api.main import app
    client = TestClient(app)
    r = client.get("/animes?status=finished")
    assert r.status_code == 200


def test_api_status_omitted_accepted():
    from api.main import app
    client = TestClient(app)
    r = client.get("/animes")
    assert r.status_code == 200


# ---- API: schemas expostos ----

def test_api_episode_schema_has_url_cdn2():
    """EpisodeOut schema deve ter campo url_cdn2."""
    from api.schemas import EpisodeOut
    fields = EpisodeOut.model_fields
    assert "url_cdn2" in fields


def test_api_episode_available_sources_three_labels():
    """available_sources deve incluir cdn1, cdn2 e animefire quando presentes."""
    from api.schemas import EpisodeOut
    ep = EpisodeOut(
        id=1, anime_id=1, numero=1,
        url_cdn="https://cdn-s01.x/o/one/01.m3u8",
        url_cdn2="https://pixel-sus.x/o/one/01.m3u8",
        url_af="https://blogger.com/x",
        available_sources=["cdn1", "cdn2", "animefire"],
    )
    assert ep.available_sources == ["cdn1", "cdn2", "animefire"]
