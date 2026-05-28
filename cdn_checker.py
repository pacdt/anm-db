import asyncio
import logging
import aiohttp

logger = logging.getLogger("CDN")

CDN_DOMAINS = [
    "cdn-s01.mywallpaper-4k-image.net",
    "pixel-sus-4k-image.com",
]

CDN_TIMEOUT = 8


def format_ep(numero: int) -> str:
    return str(numero).zfill(2)


def build_url(domain: str, slug: str, ep: int) -> str:
    return f"https://{domain}/stream/{slug[0]}/{slug}/{format_ep(ep)}.mp4/index.m3u8"


async def head_request(url: str, session: aiohttp.ClientSession) -> int | None:
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=CDN_TIMEOUT), ssl=False) as resp:
            return resp.status
    except Exception:
        return None


async def check_cdn_episode(slug: str, numero: int, session: aiohttp.ClientSession) -> str | None:
    urls = [build_url(d, slug, numero) for d in CDN_DOMAINS]
    tasks = [head_request(u, session) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for url, result in zip(urls, results):
        if isinstance(result, int) and result == 200:
            return url

    return None
