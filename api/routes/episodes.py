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
