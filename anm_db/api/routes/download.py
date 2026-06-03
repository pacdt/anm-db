"""
Rota: /download

Stream de episodios de anime com ffmpeg pipe (sem disco).

Query params:
- source: auto (padrao) | cdn | af
- format:  mp4 (padrao, ffmpeg) | ts | hls

Resolucao:
1. CDN (HLS .m3u8) -> ffmpeg -c copy para MP4/TS (baixo CPU, sem disco)
2. AF (Blogger)   -> resolve URL real do Blogger -> MP4 direto
3. Fallback       -> HLS cru (sem ffmpeg)
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from anm_db.api.deps import get_db
from anm_db.repository.database import DatabaseManager
from anm_db.services.downloader import VideoDownloader

logger = logging.getLogger("Download")

router = APIRouter(prefix="/download", tags=["download"])

Source = Literal["auto", "cdn", "cdn1", "cdn2", "af"]
Format = Literal["mp4", "ts", "hls"]


def _format_content_type(fmt: Format) -> str:
    return {
        "mp4": "video/mp4",
        "ts": "video/mp2t",
        "hls": "application/x-mpegurl",
    }[fmt]


@router.get("/{slug}/{numero}")
async def download_episode(
    slug: str,
    numero: int,
    source: Source = Query("auto"),
    format: Format = Query("mp4"),
    db: DatabaseManager = Depends(get_db),
):
    downloader = VideoDownloader(db)

    # Anotar metadados do episodio
    anime = await db.get_anime_by_slug(slug)
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found")

    result = await downloader.resolve(slug, numero, source=source)
    if not result:
        raise HTTPException(
            status_code=502,
            detail=f"No video source available for {slug}/{numero}",
        )

    # Determina nome de arquivo e content-type pelo formato pedido
    ext = format
    filename = f"{slug}-ep{numero}.{ext}"
    content_type = _format_content_type(format)

    # Se pediu hls e CDN e HLS, usa nome .m3u8
    if format == "hls":
        filename = f"{slug}-ep{numero}.m3u8"

    logger.info(
        f"Download {slug}/{numero} source={result.source_used} "
        f"fmt={format} url={result.url[:80]}"
    )

    return StreamingResponse(
        downloader.stream(result, output_format=format),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Source": result.source_used,
            "X-Transcoded": str(result.transcoded).lower(),
        },
    )
