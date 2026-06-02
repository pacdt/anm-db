"""Testes do mapa de traducao de generos."""

import pytest
from anm_db.scrapers.genre_translator import (
    DEMOGRAPHIC_PT_MAP,
    GENRE_PT_MAP,
    THEME_PT_MAP,
    all_known,
    translate_genre,
)


def test_main_genres():
    assert translate_genre("Action") == "Ação"
    assert translate_genre("Adventure") == "Aventura"
    assert translate_genre("Comedy") == "Comédia"
    assert translate_genre("Fantasy") == "Fantasia"
    assert translate_genre("Sci-Fi") == "Ficção Científica"
    assert translate_genre("Slice of Life") == "Slice of Life"  # mantido
    assert translate_genre("Mystery") == "Mistério"
    assert translate_genre("Suspense") == "Suspense"
    assert translate_genre("Horror") == "Terror"
    assert translate_genre("Ecchi") == "Ecchi"  # mantido
    assert translate_genre("Hentai") == "Hentai"  # mantido


def test_demographics():
    assert translate_genre("Shounen") == "Shounen"  # mantido
    assert translate_genre("Kids") == "Infantil"
    assert translate_genre("Josei") == "Josei"
    assert translate_genre("Seinen") == "Seinen"
    assert translate_genre("Shoujo") == "Shoujo"


def test_themes():
    assert translate_genre("Psychological") == "Psicológico"
    assert translate_genre("Mecha") == "Mecha"
    assert translate_genre("Harem") == "Harém"
    assert translate_genre("Mahou Shoujo") == "Garota Mágica"
    assert translate_genre("Super Power") == "Superpoderes"
    assert translate_genre("Time Travel") == "Viagem no Tempo"
    assert translate_genre("Historical") == "Histórico"
    assert translate_genre("School") == "Escolar"
    assert translate_genre("Military") == "Militar"


def test_unknown_fallback():
    """Genero desconhecido retorna o original."""
    assert translate_genre("Unknown Genre XYZ") == "Unknown Genre XYZ"


def test_empty_input():
    assert translate_genre("") == ""
    assert translate_genre(None) is None


def test_all_known_includes_three_maps():
    known = all_known()
    assert "Action" in known
    assert "Shounen" in known
    assert "Mecha" in known
    assert known == set(GENRE_PT_MAP) | set(DEMOGRAPHIC_PT_MAP) | set(THEME_PT_MAP)


def test_21_main_genres():
    """Garante que temos pelo menos os 21 generos principais do Jikan."""
    assert len(GENRE_PT_MAP) >= 21


def test_demographics_complete():
    """5 demographics."""
    assert len(DEMOGRAPHIC_PT_MAP) >= 5


def test_themes_substantial():
    """Cobertura razoavel de temas (>= 40)."""
    assert len(THEME_PT_MAP) >= 40
