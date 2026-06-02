"""
Rota: /episodes

Lista episodios mais recentes e episodios de um anime especifico.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from anm_db.api.schemas import EpisodeOut
from anm_db.api.deps import get_db
from anm_db.repository.database import DatabaseManager

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.get("/latest")
async def latest_episodes(
    limit: int = Query(50, ge=1, le=200),
    lang: str = Query("pt-BR", pattern="^(pt-BR|en|ja|original)$"),
    db: DatabaseManager = Depends(get_db),
):
    episodes = await db.get_latest_episodes(limit)
    items = []
    for e in episodes:
        if lang == "pt-BR":
            titulo = e.get("titulo_pt") or e.get("titulo")
        else:
            titulo = e.get("titulo")
        available = []
        if e.get("url_cdn"):
            available.append("cdn")
        if e.get("url_af"):
            available.append("animefire")
        items.append(
            EpisodeOut(
                id=e["id"],
                anime_id=e["anime_id"],
                numero=e["numero"],
                titulo=titulo,
                titulo_pt=e.get("titulo_pt"),
                url_cdn=e.get("url_cdn"),
                url_af=e.get("url_af"),
                fonte_ativa=e.get("fonte_ativa"),
                slug=e.get("slug"),
                anime_title=e.get("titulo"),
                anime_image=e.get("imagem"),
                tipo=e.get("tipo"),
                available_sources=available,
            ).model_dump()
        )
    return items


@router.get("/{slug}")
async def episodes_by_anime(
    slug: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    lang: str = Query("pt-BR", pattern="^(pt-BR|en|ja|original)$"),
    db: DatabaseManager = Depends(get_db),
):
    anime = await db.get_anime_by_slug(slug)
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found")

    episodes = await db.get_episodios_paginados(slug, page, limit)
    total = await db.get_episodios_count(slug)
    skip_times_map = await db.get_skip_times_for_anime(anime["id"])
    pages = (total + limit - 1) // limit

    items = []
    for e in episodes:
        if lang == "pt-BR":
            titulo = e.get("titulo_pt") or e.get("titulo")
        else:
            titulo = e.get("titulo")
        available = []
        if e.get("url_cdn"):
            available.append("cdn")
        if e.get("url_af"):
            available.append("animefire")
        items.append({
            "id": e["id"],
            "anime_id": e["anime_id"],
            "numero": e["numero"],
            "titulo": titulo,
            "titulo_pt": e.get("titulo_pt"),
            "url_cdn": e.get("url_cdn"),
            "url_af": e.get("url_af"),
            "fonte_ativa": e.get("fonte_ativa"),
            "slug": slug,
            "anime_title": anime.get("titulo"),
            "anime_image": anime.get("imagem"),
            "tipo": anime.get("tipo"),
            "skip_times": skip_times_map.get(e["numero"], {}),
            "available_sources": available,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
    }
