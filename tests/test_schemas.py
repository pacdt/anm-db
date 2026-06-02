"""
Testes do helper pick_lang() e schemas Pydantic.
"""

import pytest
from anm_db.api.schemas import (
    AnimeDetail,
    AnimeSummary,
    EpisodeOut,
    GeneroOut,
    PaginatedResponse,
    pick_lang,
)


class TestPickLang:
    def test_returns_first_value(self):
        assert pick_lang("PT", "EN", "JP", lang="pt-BR") == "PT"

    def test_falls_back_to_pt(self):
        # values[0] = None (idioma atual), values[1] = PT (fallback)
        assert pick_lang(None, "Portugues", "EN", lang="pt-BR") == "Portugues"

    def test_falls_back_to_original(self):
        # Se PT e EN estao vazios, cai para o original
        assert pick_lang(None, None, "Original") == "Original"

    def test_prefers_first_non_null(self):
        # values[0] e primary, depois PT, depois original
        assert pick_lang("EN", "PT", "JP") == "EN"

    def test_all_none_returns_none(self):
        assert pick_lang(None, None, None) is None

    def test_empty_args_returns_none(self):
        assert pick_lang() is None

    def test_handles_empty_string_as_falsy(self):
        assert pick_lang("", "PT") == "PT"


class TestAnimeSummary:
    def test_serializes_with_translated_flag(self):
        a = AnimeSummary(
            slug="naruto",
            title="Naruto",
            title_original="NARUTO -ナルト-",
            image="https://example.com/naruto.jpg",
            score=8.5,
            type="TV",
            translated=True,
        )
        d = a.model_dump()
        assert d["slug"] == "naruto"
        assert d["translated"] is True

    def test_defaults(self):
        a = AnimeSummary(slug="x")
        assert a.title is None
        assert a.translated is False


class TestGeneroOut:
    def test_serializes(self):
        g = GeneroOut(nome="Action", nome_pt="Acao", count=42)
        d = g.model_dump()
        assert d["nome"] == "Action"
        assert d["nome_pt"] == "Acao"
        assert d["count"] == 42


class TestEpisodeOut:
    def test_serializes_with_skip_times(self):
        e = EpisodeOut(
            id=1,
            anime_id=1,
            numero=1,
            titulo="Ep 1",
            url_cdn="https://cdn.example.com/ep1.m3u8",
            skip_times={"op": {"start": 0, "end": 90}},
            available_sources=["cdn", "animefire"],
        )
        d = e.model_dump()
        assert d["numero"] == 1
        assert d["skip_times"]["op"]["end"] == 90
        assert "cdn" in d["available_sources"]


class TestPaginatedResponse:
    def test_serializes(self):
        p = PaginatedResponse(items=[], total=0, page=1, limit=30, pages=0)
        d = p.model_dump()
        assert d["total"] == 0
        assert d["pages"] == 0
