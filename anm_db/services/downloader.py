"""
Servico de download de episodios.

Comportamento por formato:
- mp4 (CDN HLS): pipe ffmpeg -i <m3u8> -c copy -bsf:v h264_mp4toannexb -f mpegts pipe:1
  -> remux sem reencodar, baixo CPU, sem disco
- mp4 (AF direto): stream aiohttp direto para o cliente (Blogger ja e MP4)
- ts: stream direto do m3u8 servido como MPEG-TS
- hls: stream do manifesto .m3u8 cru

Em caso de erro ou ffmpeg indisponivel, faz fallback para hls cru.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from typing import AsyncIterator, Literal

import aiohttp

from anm_db.config import get_settings
from anm_db.repository.database import DatabaseManager
from anm_db.scrapers.blogger import resolve_blogger_url

logger = logging.getLogger("Downloader")


Source = Literal["auto", "cdn", "af"]
Format = Literal["mp4", "ts", "hls"]


@dataclass
class DownloadResult:
    """Resultado de uma resolucao de URL."""
    url: str
    content_type: str
    filename: str
    source_used: Source
    transcoded: bool


class FFmpegNotAvailable(Exception):
    """ffmpeg nao encontrado no PATH."""


class VideoDownloader:
    """Orquestra download de episodios com ffmpeg pipe + fallback."""

    CDN_DOMAINS = ("cdn-s01.mywallpaper-4k-image.net", "pixel-sus-4k-image.com")

    def __init__(self, db: DatabaseManager, ffmpeg_path: str | None = None):
        self.db = db
        settings = get_settings()
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path
        self.chunk_size = settings.download_chunk_size
        self.af_timeout = 30
        self.cdn_timeout = 30

    @property
    def ffmpeg_available(self) -> bool:
        return bool(self.ffmpeg_path) and shutil.which(self.ffmpeg_path) is not None

    def _is_hls(self, url: str) -> bool:
        return ".m3u8" in url.lower() or "mpegurl" in url.lower()

    def _is_cdn(self, url: str) -> bool:
        return any(d in url for d in self.CDN_DOMAINS)

    async def resolve(
        self,
        slug: str,
        numero: int,
        source: Source = "auto",
    ) -> DownloadResult | None:
        """Resolve a URL final do episodio, escolhendo CDN ou AF."""
        anime = await self.db.get_anime_by_slug(slug)
        if not anime:
            return None
        episode = await self._get_episode(slug, numero)
        if not episode:
            return None

        # Tenta CDN primeiro
        if source in ("auto", "cdn") and episode.get("url_cdn"):
            return DownloadResult(
                url=episode["url_cdn"],
                content_type="video/mp4",
                filename=f"{slug}-ep{numero}.mp4",
                source_used="cdn",
                transcoded=self._is_hls(episode["url_cdn"]),
            )

        # Fallback AF (Blogger)
        if source in ("auto", "af") and episode.get("url_af"):
            af_url = episode["url_af"]
            if not af_url.startswith("http"):
                return None
            # Se for Blogger token URL, resolve para MP4 real
            if "blogger.com/video.g" in af_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        resolved = await resolve_blogger_url(af_url, session)
                    if resolved:
                        return DownloadResult(
                            url=resolved,
                            content_type="video/mp4",
                            filename=f"{slug}-ep{numero}.mp4",
                            source_used="af",
                            transcoded=False,
                        )
                except Exception as e:
                    logger.warning(f"Falha ao resolver Blogger URL: {e}")
            else:
                # URL direta (ja e MP4 ou HLS)
                return DownloadResult(
                    url=af_url,
                    content_type="application/x-mpegurl" if self._is_hls(af_url) else "video/mp4",
                    filename=f"{slug}-ep{numero}.{'m3u8' if self._is_hls(af_url) else 'mp4'}",
                    source_used="af",
                    transcoded=False,
                )

        return None

    async def _get_episode(self, slug: str, numero: int) -> dict | None:
        eps = await self.db.get_episodios_paginados(slug, page=1, limit=10000)
        for e in eps:
            if e["numero"] == numero:
                return e
        return None

    async def stream(
        self,
        result: DownloadResult,
        output_format: Format = "mp4",
    ) -> AsyncIterator[bytes]:
        """Faz streaming do episodio no formato pedido.

        Para mp4/ts de HLS: usa ffmpeg pipe (baixo CPU, sem disco).
        Para hls cru: stream do manifesto original.
        Para MP4 direto: stream aiohttp direto.
        """
        url = result.url

        # HLS cru (sem transcode)
        if output_format == "hls":
            async for chunk in self._stream_direct(url, result.content_type):
                yield chunk
            return

        # MP4 ou TS a partir de HLS via ffmpeg pipe
        if self._is_hls(url) and output_format in ("mp4", "ts") and self.ffmpeg_available:
            try:
                async for chunk in self._stream_ffmpeg_pipe(url, output_format):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"ffmpeg falhou, tentando fallback HLS cru: {e}")
                # Fallback: stream HLS cru
                async for chunk in self._stream_direct(url, "application/x-mpegurl"):
                    yield chunk
                return

        # MP4 direto (sem ffmpeg)
        if output_format == "mp4" and not self._is_hls(url):
            async for chunk in self._stream_direct(url, "video/mp4"):
                yield chunk
            return

        # TS pedido mas URL nao e HLS: faz wrap em TS via ffmpeg
        if output_format == "ts" and not self._is_hls(url) and self.ffmpeg_available:
            try:
                async for chunk in self._stream_ffmpeg_pipe(url, "ts"):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"ffmpeg wrap-to-ts falhou: {e}")

        # Fallback final
        async for chunk in self._stream_direct(url, result.content_type):
            yield chunk

    async def _stream_direct(self, url: str, content_type: str) -> AsyncIterator[bytes]:
        """Stream direto via aiohttp."""
        try:
            timeout = aiohttp.ClientTimeout(total=self.cdn_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, ssl=False, allow_redirects=True) as resp:
                    if resp.status != 200:
                        logger.error(f"Stream HTTP {resp.status} para {url[:80]}")
                        return
                    async for chunk in resp.content.iter_chunked(self.chunk_size):
                        if chunk:
                            yield chunk
        except asyncio.TimeoutError:
            logger.error(f"Stream timeout para {url[:80]}")
        except Exception as e:
            logger.error(f"Erro no stream: {e}")

    async def _stream_ffmpeg_pipe(
        self, url: str, output_format: Format
    ) -> AsyncIterator[bytes]:
        """Usa ffmpeg via pipe para transcode/remux sem usar disco.

        Para HLS -> MP4: -c copy (sem reencodar)
        Para HLS -> TS:  -c copy
        Para MP4 -> TS:  -c copy (wrap em mpegts)
        """
        if not self.ffmpeg_available:
            raise FFmpegNotAvailable(f"ffmpeg nao encontrado em '{self.ffmpeg_path}'")

        if output_format == "mp4":
            # H264 em MP4 precisa de h264_mp4toannexb para streamable
            vf_args = [
                "-loglevel", "error",
                "-i", url,
                "-c", "copy",
                "-bsf:v", "h264_mp4toannexb",
                "-f", "mpegts",
                "pipe:1",
            ]
        elif output_format == "ts":
            vf_args = [
                "-loglevel", "error",
                "-i", url,
                "-c", "copy",
                "-f", "mpegts",
                "pipe:1",
            ]
        else:
            raise ValueError(f"Formato nao suportado para ffmpeg: {output_format}")

        logger.debug(f"ffmpeg {' '.join(vf_args)}")
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg_path,
                *vf_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise FFmpegNotAvailable(f"ffmpeg nao encontrado: {e}") from e

        try:
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                await proc.wait()
            except Exception:
                pass
            if proc.returncode not in (0, None):
                stderr = b""
                try:
                    stderr = await asyncio.wait_for(proc.stderr.read(), timeout=1.0)
                except Exception:
                    pass
                logger.error(
                    f"ffmpeg exit code {proc.returncode} apos "
                    f"{time.monotonic() - start:.1f}s: {stderr.decode(errors='ignore')[:200]}"
                )
            else:
                logger.info(
                    f"ffmpeg stream concluido em {time.monotonic() - start:.1f}s"
                )
