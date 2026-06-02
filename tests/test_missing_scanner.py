"""Testes para o servico de deteccao de animes faltantes."""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock

from anm_db.repository.database import DatabaseManager
from anm_db.services.missing_scanner import MissingEpisodeScanner


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


async def test_scan_no_animes(db):
    """Banco vazio: scanner retorna relatorio zerado sem erro."""
    mock_scraper = MagicMock()
    mock_scraper.atualizar_anime = AsyncMock(return_value=(0, False, 0, 0))
    scanner = MissingEpisodeScanner(db, scraper=mock_scraper)
    report = await scanner.scan(limit=100)
    assert report.total_scanned == 0
    assert report.without_eps == 0
    assert report.with_gaps == 0


async def test_scan_anime_without_episodes(db):
    """Anime com 0 episodios e detectado."""
    await db.upsert_anime({
        "slug": "no-eps",
        "tipo": "legendado",
        "status": "finished",
    })

    # Mock scraper que nao faz nada
    mock_scraper = MagicMock()
    mock_scraper.atualizar_anime = AsyncMock(return_value=(0, False, 0, 0))

    scanner = MissingEpisodeScanner(db, scraper=mock_scraper)
    report = await scanner.scan(limit=10)

    assert report.without_eps == 1
    assert report.total_scanned == 1
    assert mock_scraper.atualizar_anime.called


async def test_scan_calls_scraper_for_each_anime(db):
    """Cada anime faltante e passado para o scraper."""
    for i in range(3):
        await db.upsert_anime({
            "slug": f"empty-{i}",
            "tipo": "legendado",
        })

    mock_scraper = MagicMock()
    mock_scraper.atualizar_anime = AsyncMock(return_value=(2, True, 1, 1))

    scanner = MissingEpisodeScanner(db, scraper=mock_scraper)
    report = await scanner.scan(limit=10)

    assert report.total_scanned == 3
    assert mock_scraper.atualizar_anime.call_count == 3
    assert report.eps_added == 6  # 2 eps * 3 animes
    assert report.cdn_hits == 3
    assert report.af_fallbacks == 3
