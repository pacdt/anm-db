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


async def check_all_cdn_episodes(
    slug: str,
    numero: int,
    session: aiohttp.ClientSession,
) -> dict[str, str]:
    """Verifica TODAS as CDNs configuradas e retorna dict {domain: url}
    apenas para as fontes que responderam 200.

    Permite armazenar multiplas fontes de video para o mesmo episodio.
    """
    urls = {d: build_url(d, slug, numero) for d in CDN_DOMAINS}
    tasks = [head_request(url, session) for url in urls.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    working: dict[str, str] = {}
    for domain, url in urls.items():
        result = results[list(urls.keys()).index(domain)]
        if isinstance(result, int) and result == 200:
            working[domain] = url
    return working


async def check_cdn_episode(slug: str, numero: int, session: aiohttp.ClientSession) -> str | None:
    """Mantida para retrocompatibilidade. Retorna a PRIMEIRA fonte CDN disponivel.

    Para checar TODAS as fontes, use check_all_cdn_episodes().
    """
    sources = await check_all_cdn_episodes(slug, numero, session)
    for url in sources.values():
        return url
    return None
