from fastapi import APIRouter, Depends, Query
from api.schemas import AnimeSummary, AnimeDetail, PaginatedResponse
from api.deps import get_db
from db import DatabaseManager

router = APIRouter(prefix="/animes", tags=["animes"])


@router.get("", response_model=PaginatedResponse)
async def list_animes(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    status: str = Query(None),
    search: str = Query(None),
    db: DatabaseManager = Depends(get_db),
):
    animes = await db.list_animes_paginado(page, limit, status, search)
    total = await db.count_animes(status)
    pages = (total + limit - 1) // limit

    items = [
        AnimeSummary(
            title=a.get("titulo_en") or a.get("titulo"),
            slug=a["slug"],
            image=a.get("imagem"),
            score=a.get("score"),
            type=a.get("tipo"),
        ).model_dump()
        for a in animes
    ]

    return PaginatedResponse(
        items=items, total=total, page=page, limit=limit, pages=pages
    )


@router.get("/{slug}", response_model=AnimeDetail)
async def get_anime(slug: str, db: DatabaseManager = Depends(get_db)):
    anime = await db.get_anime_by_slug(slug)
    if not anime:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Anime not found")

    genres = await db.get_generos_by_slug(slug)
    eps = await db.get_episodios_paginados(slug, page=1, limit=10000)
    skip_times_map = await db.get_skip_times_for_anime(anime["id"])

    episodes = []
    for e in eps:
        ep_num = e["numero"]
        episodes.append({
            "numero": ep_num,
            "titulo": e.get("titulo"),
            "url_cdn": e.get("url_cdn"),
            "url_af": e.get("url_af"),
            "fonte_ativa": e.get("fonte_ativa"),
            "skip_times": skip_times_map.get(ep_num, {}),
        })

    return AnimeDetail(
        id=anime["id"],
        mal_id=anime.get("mal_id"),
        slug=anime["slug"],
        tipo=anime.get("tipo"),
        titulo=anime.get("titulo"),
        titulo_en=anime.get("titulo_en"),
        titulo_jp=anime.get("titulo_jp"),
        imagem=anime.get("imagem"),
        score=anime.get("score"),
        sinopse=anime.get("sinopse"),
        trailer_url=anime.get("trailer_url"),
        status=anime.get("status"),
        genres=genres,
        episodes=episodes,
    )
