"""
Schemas Pydantic da API.

Suporta i18n via parametro `lang` (pt-BR | en | original | ja).
Por padrao, campos `titulo` e `sinopse` retornam PT-BR quando disponivel.
O original Jikan fica em `titulo_original` / `sinopse_original` para o
cliente poder comparar / fazer fallback.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Lang = Literal["pt-BR", "en", "original", "ja"]


def pick_lang(
    *values: str | None,
    lang: str = "pt-BR",
) -> str | None:
    """Seleciona o valor de acordo com o idioma preferido.

    Ordem de fallback: idioma solicitado -> PT-BR -> EN (titulo_en) -> original.
    """
    # values[0] = idioma solicitado (pt/en/ja), values[1] = pt-BR, values[2] = original
    if not values:
        return None
    primary, *fallbacks = values
    return primary or _first_non_null(fallbacks)


def _first_non_null(values: tuple[str | None, ...]) -> str | None:
    for v in values:
        if v:
            return v
    return None


# ---- Generos ----

class GeneroOut(BaseModel):
    """Genero com nome original (EN) e nome PT-BR."""
    nome: str
    nome_pt: str
    count: int = 0


# ---- Anime ----

class AnimeSummary(BaseModel):
    """Resumo do anime (lista)."""
    slug: str
    title: str | None = None                # idioma atual (padrao pt-BR)
    title_original: str | None = None       # sempre Jikan original
    image: str | None = None
    score: float | None = None
    type: str | None = None
    translated: bool = False


class AnimeDetail(BaseModel):
    """Detalhe completo do anime."""
    id: int
    mal_id: int | None = None
    slug: str
    tipo: str | None = None

    # Titulo (multi-idioma)
    titulo: str | None = None                # idioma atual
    titulo_original: str | None = None       # Jikan 'title'
    titulo_pt: str | None = None             # Gemini
    titulo_en: str | None = None             # Jikan 'title_english'
    titulo_jp: str | None = None             # Jikan 'title_japanese'

    imagem: str | None = None
    score: float | None = None

    # Sinopse (multi-idioma)
    sinopse: str | None = None               # idioma atual
    sinopse_original: str | None = None      # Jikan 'synopsis'
    sinopse_pt: str | None = None            # Gemini

    trailer_url: str | None = None
    status: str | None = None
    translated: bool = False                 # True se tem titulo_pt OU sinopse_pt
    translation_model: str | None = None
    translated_at: str | None = None

    genres: list[GeneroOut] = []
    episodes: list["EpisodeOut"] = []


# ---- Episodios ----

class EpisodeOut(BaseModel):
    id: int
    anime_id: int
    numero: int
    titulo: str | None = None
    titulo_pt: str | None = None
    url_cdn: str | None = None
    url_cdn2: str | None = None
    url_af: str | None = None
    fonte_ativa: str | None = None
    slug: str | None = None
    anime_title: str | None = None
    anime_image: str | None = None
    tipo: str | None = None
    skip_times: dict = Field(default_factory=dict)
    available_sources: list[str] = Field(default_factory=list)


# ---- Paginacao ----

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    limit: int
    pages: int


# ---- Resolucao forward ----
AnimeDetail.model_rebuild()
