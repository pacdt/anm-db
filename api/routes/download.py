import logging
import aiohttp
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from api.deps import get_db
from db import DatabaseManager
from blogspot_video import resolve_blogger_url

logger = logging.getLogger("Download")

router = APIRouter(prefix="/download", tags=["download"])

CHUNK_SIZE = 1024 * 64
CDN_TIMEOUT = 30
AF_TIMEOUT = 30


@router.get("/{slug}/{numero}")
async def download_episode(
    slug: str,
    numero: int,
    source: str = Query("auto", pattern="^(auto|cdn|af)$"),
    db: DatabaseManager = Depends(get_db),
):
    anime = await db.get_anime_by_slug(slug)
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found")

    episode = await _get_episode(db, slug, numero)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    video_url = None
    content_type = None

    if source in ("auto", "cdn"):
        video_url = episode.get("url_cdn")
        if video_url:
            content_type = "application/x-mpegurl"

    if not video_url and source in ("auto", "af"):
        af_url = episode.get("url_af")
        if af_url:
            resolved = await _resolve_af_url(af_url)
            if resolved:
                video_url = resolved
                content_type = "video/mp4"
            else:
                logger.warning(f"Falha ao resolver AF para {slug}/{numero}")

    if not video_url:
        raise HTTPException(status_code=502, detail="No video source available")

    filename = f"{slug}-ep{numero}.mp4"
    if source == "cdn" or (source == "auto" and episode.get("fonte_ativa") == "cdn"):
        filename = f"{slug}-ep{numero}.m3u8"

    return StreamingResponse(
        _stream_video(video_url),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


async def _get_episode(db: DatabaseManager, slug: str, numero: int) -> dict | None:
    eps = await db.get_episodios_paginados(slug, page=1, limit=10000)
    for ep in eps:
        if ep["numero"] == numero:
            return ep
    return None


async def _resolve_af_url(af_url: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            return await resolve_blogger_url(af_url, session)
    except Exception as e:
        logger.error(f"Erro ao resolver AF URL: {e}")
        return None


async def _stream_video(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=CDN_TIMEOUT),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Video HTTP {resp.status} para {url[:80]}")
                    return

                async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                    yield chunk
    except Exception as e:
        logger.error(f"Erro ao streamar video: {e}")
