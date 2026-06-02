"""Testes para o servico de traducao PT-BR."""

import pytest
import json
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

from anm_db.repository.database import DatabaseManager
from anm_db.services.translator import AnimeTranslator, TranslationReport
from anm_db.scrapers.gemini import GeminiClient, GeminiQuotaExceeded


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


async def test_translator_no_api_key(db):
    """Sem API key: marca todos como skipped_no_key."""
    # Insere 3 animes
    for i in range(3):
        await db.upsert_anime({
            "slug": f"test-{i}",
            "tipo": "legendado",
            "titulo": f"Test {i}",
            "sinopse": "Lorem ipsum.",
        })

    gemini = GeminiClient(api_key=None)
    translator = AnimeTranslator(db, gemini=gemini, batch_size=10)
    report = await translator.translate_pending()

    assert report.total == 3
    assert report.skipped == 3
    assert report.translated == 0

    # Garante que nada foi traduzido
    for i in range(3):
        anime = await db.get_anime_by_slug(f"test-{i}")
        assert anime["titulo_pt"] is None
        assert anime["sinopse_pt"] is None


async def test_translator_quota_exceeded(db):
    """Quota excedida no meio do batch: marca restantes como skipped_quota."""
    for i in range(15):
        await db.upsert_anime({
            "slug": f"a-{i}",
            "tipo": "legendado",
            "titulo": f"Anime {i}",
            "sinopse": "Test.",
        })

    gemini = MagicMock()
    gemini.api_key = "fake"
    gemini.model = "gemini-2.5-flash"

    call_count = 0

    async def translate_batch(items, target="pt-BR"):
        nonlocal call_count
        call_count += 1
        # Primeiro batch (10 itens): sucesso para 1 deles
        if call_count == 1:
            return [
                {
                    "id": items[0]["id"],
                    "titulo_pt": f"Traduzido {items[0]['id']}",
                    "sinopse_pt": "Traduzido",
                    "_usage": {"input": 100, "output": 50},
                }
            ]
        # Segundo batch (5 itens): quota excedida
        raise GeminiQuotaExceeded("quota")

    gemini.translate_batch = translate_batch
    translator = AnimeTranslator(db, gemini=gemini, batch_size=10)
    report = await translator.translate_pending()

    assert report.translated == 1
    # 15 total - 1 translated = 14. 9 failed (batch 1: 10-1) + 5 skipped (batch 2: quota)
    assert report.failed == 9
    assert report.skipped == 5


async def test_translator_success(db):
    """Fluxo feliz: Gemini retorna traducoes validas."""
    for i in range(3):
        await db.upsert_anime({
            "slug": f"b-{i}",
            "tipo": "legendado",
            "titulo": f"Original {i}",
            "titulo_en": f"English Title {i}",
            "sinopse": f"Synopsis of anime {i}",
        })

    gemini = MagicMock()
    gemini.api_key = "fake"
    gemini.model = "gemini-2.5-flash"

    async def translate_batch(items, target="pt-BR"):
        return [
            {
                "id": it["id"],
                "titulo_pt": f"PT {it['id']}",
                "sinopse_pt": f"PT sinopse {it['id']}",
                "_usage": {"input": 50, "output": 30},
            }
            for it in items
        ]

    gemini.translate_batch = translate_batch
    translator = AnimeTranslator(db, gemini=gemini, batch_size=10)
    report = await translator.translate_pending()

    assert report.translated == 3
    assert report.input_tokens == 150
    assert report.output_tokens == 90

    # Verifica que foi salvo no DB
    for i in range(3):
        anime = await db.get_anime_by_slug(f"b-{i}")
        assert anime["titulo_pt"] == f"PT {anime['id']}"
        assert anime["sinopse_pt"] == f"PT sinopse {anime['id']}"
        assert anime["traducao_modelo"] == "gemini-2.5-flash"
        assert anime["traduzido_em"] is not None
        # NAO sobrescreveu campos originais
        assert anime["titulo"] == f"Original {i}"
        assert anime["sinopse"] == f"Synopsis of anime {i}"


async def test_translator_idempotent(db):
    """Re-traduzir anime ja traduzido NAO sobrescreve dados."""
    await db.upsert_anime({
        "slug": "already-pt",
        "tipo": "legendado",
        "titulo": "Original",
        "sinopse": "Original sinopse",
    })
    # Simula traducao anterior
    await db.update_translation(
        anime_id=1,  # sera o ID alocado
        titulo_pt="PT antigo",
        sinopse_pt="PT sinopse antiga",
        model="gemini-2.5-flash",
    )

    # Agora tenta traduzir de novo - este anime NAO deve aparecer como pendente
    # (titulo_pt e sinopse_pt ja estao preenchidos)
    gemini = MagicMock()
    gemini.api_key = "fake"

    async def translate_batch(items, target="pt-BR"):
        pytest.fail("Gemini nao deveria ser chamado")

    gemini.translate_batch = translate_batch
    translator = AnimeTranslator(db, gemini=gemini, batch_size=10)
    report = await translator.translate_pending()

    assert report.total == 0
    assert report.translated == 0


async def test_translator_partial_pt_triggers(db):
    """Anime com titulo_pt mas sem sinopse_pt ainda precisa de traducao parcial."""
    await db.upsert_anime({
        "slug": "partial-pt",
        "tipo": "legendado",
        "titulo": "Original",
        "sinopse": "Long synopsis",
    })
    # Pega o ID alocado
    anime = await db.get_anime_by_slug("partial-pt")
    await db.update_translation(
        anime_id=anime["id"],
        titulo_pt="Titulo PT",
        sinopse_pt=None,  # sinopse ainda nao
        model="gemini-2.5-flash",
    )

    gemini = MagicMock()
    gemini.api_key = "fake"
    gemini.model = "gemini-2.5-flash"

    captured_items = []

    async def translate_batch(items, target="pt-BR"):
        captured_items.extend(items)
        return [
            {
                "id": it["id"],
                "titulo_pt": "Atualizado",
                "sinopse_pt": "Sinopse PT",
                "_usage": {"input": 10, "output": 5},
            }
            for it in items
        ]

    gemini.translate_batch = translate_batch
    translator = AnimeTranslator(db, gemini=gemini, batch_size=10)
    report = await translator.translate_pending()

    assert report.total == 1
    assert report.translated == 1
    assert len(captured_items) == 1


def test_gemini_client_available_property():
    c1 = GeminiClient(api_key=None)
    assert c1.available is False

    c2 = GeminiClient(api_key="AIza...", rpd=10)
    assert c2.available is True
    c2.daily_counter = 10
    assert c2.available is False


def test_gemini_parse_response_with_markdown():
    """Gemini as vezes retorna JSON dentro de markdown fences."""
    c = GeminiClient(api_key="x")
    text = '```json\n[{"id": 1, "titulo_pt": "T", "sinopse_pt": "S"}]\n```'
    result = c._parse_response(text, [{"id": 1, "titulo": "x", "sinopse": "y"}])
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["titulo_pt"] == "T"


def test_gemini_parse_response_with_prose():
    """Gemini pode adicionar prosa antes do JSON."""
    c = GeminiClient(api_key="x")
    text = 'Aqui esta a traducao:\n[{"id": 1, "titulo_pt": "T", "sinopse_pt": "S"}]\nEspero que ajude!'
    result = c._parse_response(text, [{"id": 1}])
    assert len(result) == 1


def test_gemini_parse_response_invalid():
    c = GeminiClient(api_key="x")
    result = c._parse_response("lixo sem json", [{"id": 1}])
    assert result == []
