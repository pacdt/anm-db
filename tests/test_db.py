import pytest
import os
import tempfile
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


async def test_init_db(db):
    assert db._db is not None


async def test_upsert_anime(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
        "titulo": "Test Anime",
    })
    assert anime_id > 0

    anime = await db.get_anime_by_slug("test-anime")
    assert anime is not None
    assert anime["slug"] == "test-anime"
    assert anime["titulo"] == "Test Anime"
    assert anime["tipo"] == "legendado"


async def test_upsert_anime_update(db):
    await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
        "titulo": "Original",
    })
    await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
        "titulo": "Updated",
    })

    anime = await db.get_anime_by_slug("test-anime")
    assert anime["titulo"] == "Updated"


async def test_upsert_episodio(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
    })

    await db.upsert_episodio(anime_id, 1, "Ep 1", url_af="http://example.com/1.mp4")

    eps = await db.get_episodios_paginados("test-anime")
    assert len(eps) == 1
    assert eps[0]["numero"] == 1
    assert eps[0]["url_af"] == "http://example.com/1.mp4"


async def test_upsert_episodio_update(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
    })

    await db.upsert_episodio(anime_id, 1, "Ep 1", url_af="http://old.mp4")
    await db.upsert_episodio(anime_id, 1, "Ep 1 Updated", url_cdn="http://cdn.mp4")

    eps = await db.get_episodios_paginados("test-anime")
    assert len(eps) == 1
    assert eps[0]["url_cdn"] == "http://cdn.mp4"
    assert eps[0]["titulo"] == "Ep 1 Updated"


async def test_get_ongoing_due(db):
    anime_id = await db.upsert_anime({
        "slug": "ongoing-1",
        "tipo": "legendado",
        "status": "ongoing",
    })

    await db.reschedule_next_check([anime_id], hours=-1)

    due = await db.get_ongoing_due()
    slugs = [a["slug"] for a in due]
    assert "ongoing-1" in slugs


async def test_list_all_slugs(db):
    await db.upsert_anime({"slug": "anime-a", "tipo": "legendado"})
    await db.upsert_anime({"slug": "anime-b", "tipo": "dublado"})

    slugs = await db.list_all_slugs()
    assert "anime-a" in slugs
    assert "anime-b" in slugs


async def test_get_ultimo_episodio(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
    })

    last = await db.get_ultimo_episodio("test-anime")
    assert last == 0

    await db.upsert_episodio(anime_id, 5, "Ep 5")
    last = await db.get_ultimo_episodio("test-anime")
    assert last == 5


async def test_generos(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
    })

    g1 = await db.upsert_genero("Action")
    g2 = await db.upsert_genero("Comedy")
    await db.link_anime_genero(anime_id, g1)
    await db.link_anime_genero(anime_id, g2)

    genres = await db.get_generos_by_slug("test-anime")
    assert "Action" in genres
    assert "Comedy" in genres


async def test_skip_times(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
    })

    await db.upsert_skip_time(anime_id, 1, "op", 5.2, 89.4)
    await db.upsert_skip_time(anime_id, 1, "ed", 1320.0, 1410.0)

    times = await db.get_skip_times(anime_id, 1)
    assert times["op"]["start"] == 5.2
    assert times["ed"]["end"] == 1410.0


async def test_job_runs(db):
    run_id = await db.log_job_start("test_job")
    assert run_id > 0

    await db.log_job_end(run_id, "success", animes_checked=10, eps_novos=3)

    async with db._db.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,)) as cur:
        row = await cur.fetchone()
        assert row["status"] == "success"
        assert row["animes_checked"] == 10
        assert row["eps_novos"] == 3


async def test_list_animes_paginado(db):
    for i in range(10):
        await db.upsert_anime({"slug": f"anime-{i:02d}", "tipo": "legendado"})

    page1 = await db.list_animes_paginado(page=1, limit=3)
    assert len(page1) == 3

    page2 = await db.list_animes_paginado(page=2, limit=3)
    assert len(page2) == 3

    total = await db.count_animes()
    assert total == 10


async def test_get_latest_episodes(db):
    anime_id = await db.upsert_anime({
        "slug": "test-anime",
        "tipo": "legendado",
    })

    await db.upsert_episodio(anime_id, 1, "Ep 1")
    await db.upsert_episodio(anime_id, 2, "Ep 2")

    latest = await db.get_latest_episodes(limit=2)
    assert len(latest) == 2


async def test_init_db_existing(db_path):
    db1 = DatabaseManager(db_path)
    await db1.init_db()
    await db1.upsert_anime({"slug": "test", "tipo": "legendado"})
    await db1.close()

    db2 = DatabaseManager(db_path)
    await db2.init_db()

    anime = await db2.get_anime_by_slug("test")
    assert anime is not None
    await db2.close()
