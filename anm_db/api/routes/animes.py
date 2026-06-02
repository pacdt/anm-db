"""
Rota: /animes

Suporta i18n via query param `lang=pt-BR|en|ja|original` (padrao pt-BR).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from anm_db.api.schemas import AnimeDetail, AnimeSummary, GeneroOut, PaginatedResponse, pick_lang
from anm_db.api.deps import get_db
from anm_db.repository.database import DatabaseManager

router = APIRouter(prefix="/animes", tags=["animes"])


@router.get("", response_model=PaginatedResponse)
async def list_animes(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    lang: str = Query("pt-BR", pattern="^(pt-BR|en|ja|original)$"),
    db: DatabaseManager = Depends(get_db),
):
    animes = await db.list_animes_paginado(page, limit, status, search)
    total = await db.count_animes(status)
    pages = (total + limit - 1) // limit

    items = []
    for a in animes:
        # Seleciona titulo baseado no idioma
        if lang == "pt-BR":
            title = a.get("titulo_pt") or a.get("titulo") or a.get("titulo_en")
        elif lang == "en":
            title = a.get("titulo_en") or a.get("titulo")
        elif lang == "ja":
            title = a.get("titulo_jp") or a.get("titulo")
        else:  # original
            title = a.get("titulo")
        items.append(
            AnimeSummary(
                slug=a["slug"],
                title=title,
                title_original=a.get("titulo"),
                image=a.get("imagem"),
                score=a.get("score"),
                type=a.get("tipo"),
                translated=bool(a.get("titulo_pt")),
            ).model_dump()
        )

    return PaginatedResponse(items=items, total=total, page=page, limit=limit, pages=pages)


@router.get("/{slug}", response_model=AnimeDetail)
async def get_anime(
    slug: str,
    lang: str = Query("pt-BR", pattern="^(pt-BR|en|ja|original)$"),
    db: DatabaseManager = Depends(get_db),
):
    anime = await db.get_anime_by_slug(slug)
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found")

    generos_rows = await db.get_generos_by_slug(slug)
    generos = [GeneroOut(nome=g["nome"], nome_pt=g["nome_pt"], count=0) for g in generos_rows]

    eps = await db.get_episodios_paginados(slug, page=1, limit=10000)
    skip_times_map = await db.get_skip_times_for_anime(anime["id"])

    episodes = []
    for e in eps:
        ep_num = e["numero"]
        # Titulo do episodio respeita lang
        if lang == "pt-BR":
            ep_titulo = e.get("titulo_pt") or e.get("titulo")
        else:
            ep_titulo = e.get("titulo")
        available = []
        if e.get("url_cdn"):
            available.append("cdn")
        if e.get("url_af"):
            available.append("animefire")
        episodes.append({
            "id": e["id"],
            "anime_id": e["anime_id"],
            "numero": ep_num,
            "titulo": ep_titulo,
            "titulo_pt": e.get("titulo_pt"),
            "url_cdn": e.get("url_cdn"),
            "url_af": e.get("url_af"),
            "fonte_ativa": e.get("fonte_ativa"),
            "skip_times": skip_times_map.get(ep_num, {}),
            "available_sources": available,
        })

    # Selecao de titulo por idioma
    if lang == "pt-BR":
        titulo = anime.get("titulo_pt") or anime.get("titulo") or anime.get("titulo_en")
        sinopse = anime.get("sinopse_pt") or anime.get("sinopse")
    elif lang == "en":
        titulo = anime.get("titulo_en") or anime.get("titulo")
        sinopse = anime.get("sinopse")
    elif lang == "ja":
        titulo = anime.get("titulo_jp") or anime.get("titulo")
        sinopse = anime.get("sinopse")
    else:  # original
        titulo = anime.get("titulo")
        sinopse = anime.get("sinopse")

    return AnimeDetail(
        id=anime["id"],
        mal_id=anime.get("mal_id"),
        slug=anime["slug"],
        tipo=anime.get("tipo"),
        titulo=titulo,
        titulo_original=anime.get("titulo"),
        titulo_pt=anime.get("titulo_pt"),
        titulo_en=anime.get("titulo_en"),
        titulo_jp=anime.get("titulo_jp"),
        imagem=anime.get("imagem"),
        score=anime.get("score"),
        sinopse=sinopse,
        sinopse_original=anime.get("sinopse"),
        sinopse_pt=anime.get("sinopse_pt"),
        trailer_url=anime.get("trailer_url"),
        status=anime.get("status"),
        translated=bool(anime.get("sinopse_pt") or anime.get("titulo_pt")),
        translation_model=anime.get("traducao_modelo"),
        translated_at=anime.get("traduzido_em"),
        genres=generos,
        episodes=episodes,
    )
