import pytest
import tempfile
import os
from db import DatabaseManager
from jikan import JikanSync


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


def test_extract_anime_data():
    jikan = JikanSync.__new__(JikanSync)
    jikan_anime = {
        "mal_id": 12345,
        "title": "Test Anime",
        "title_english": "Test Anime EN",
        "title_japanese": "テストアニメ",
        "images": {"webp": {"large_image_url": "https://example.com/img.webp"}},
        "score": 8.5,
        "synopsis": "A test anime synopsis",
        "trailer": {"url": "https://youtube.com/watch?v=abc"},
    }
    result = jikan._extract_anime_data(jikan_anime)
    assert result["mal_id"] == 12345
    assert result["titulo"] == "Test Anime"
    assert result["titulo_en"] == "Test Anime EN"
    assert result["titulo_jp"] == "テストアニメ"
    assert result["score"] == 8.5
    assert result["sinopse"] == "A test anime synopsis"
    assert result["trailer_url"] == "https://youtube.com/watch?v=abc"
    assert result["status"] == "ongoing"


def test_extract_genres():
    jikan = JikanSync.__new__(JikanSync)
    jikan_anime = {
        "genres": [
            {"mal_id": 1, "name": "Action"},
            {"mal_id": 2, "name": "Comedy"},
        ]
    }
    result = jikan._extract_genres(jikan_anime)
    assert result == ["Action", "Comedy"]


def test_extract_genres_empty():
    jikan = JikanSync.__new__(JikanSync)
    result = jikan._extract_genres({})
    assert result == []


def test_extract_anime_data_minimal():
    jikan = JikanSync.__new__(JikanSync)
    result = jikan._extract_anime_data({})
    assert result["mal_id"] is None
    assert result["titulo"] is None
    assert result["status"] == "ongoing"
