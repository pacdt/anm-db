from fastapi import APIRouter, Depends, Query
from api.schemas import EpisodeOut
from api.deps import get_db
from db import DatabaseManager

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.get("/latest")
async def latest_episodes(
    limit: int = Query(50, ge=1, le=200),
    db: DatabaseManager = Depends(get_db),
):
    episodes = await db.get_latest_episodes(limit)
    return [
        EpisodeOut(
            id=e["id"],
            anime_id=e["anime_id"],
            numero=e["numero"],
            titulo=e.get("titulo"),
            url_cdn=e.get("url_cdn"),
            url_af=e.get("url_af"),
            fonte_ativa=e.get("fonte_ativa"),
            slug=e.get("slug"),
            anime_title=e.get("titulo"),
            anime_image=e.get("imagem"),
            tipo=e.get("tipo"),
        ).model_dump()
        for e in episodes
    ]


@router.get("/{slug}")
async def episodes_by_anime(
    slug: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: DatabaseManager = Depends(get_db),
):
    anime = await db.get_anime_by_slug(slug)
    if not anime:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Anime not found")

    episodes = await db.get_episodios_paginados(slug, page, limit)
    total = await db.get_episodios_count(slug)
    skip_times_map = await db.get_skip_times_for_anime(anime["id"])
    pages = (total + limit - 1) // limit

    items = []
    for e in episodes:
        ep_num = e["numero"]
        ep_data = {
            "id": e["id"],
            "anime_id": e["anime_id"],
            "numero": ep_num,
            "titulo": e.get("titulo"),
            "url_cdn": e.get("url_cdn"),
            "url_af": e.get("url_af"),
            "fonte_ativa": e.get("fonte_ativa"),
            "slug": slug,
            "anime_title": anime.get("titulo"),
            "anime_image": anime.get("imagem"),
            "tipo": anime.get("tipo"),
            "skip_times": skip_times_map.get(ep_num, {}),
        }
        items.append(ep_data)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
    }
