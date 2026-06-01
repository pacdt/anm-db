import re
import logging
from html.parser import HTMLParser
import aiohttp

logger = logging.getLogger("Blogspot")

BLOGGER_TIMEOUT = 15

_REGEX_PATTERNS = [
    re.compile(r'(https?://[^"\'<>\s]+\.bp\.blogspot\.com[^"\'<>\s]+\.(?:mp4|m3u8))'),
    re.compile(r'(https?://[^"\'<>\s]+\.googleusercontent\.com[^"\'<>\s]+\.(?:mp4|m3u8))'),
    re.compile(r'"(https?://[^"\'<>\s]+video[^"\'<>\s]*)"'),
    re.compile(r'source\s+src="([^"]+)"'),
    re.compile(r'file\s*:\s*["\']([^"\']+)["\']'),
    re.compile(r'"url"\s*:\s*"([^"]+)"'),
    re.compile(r'"videoUrl"\s*:\s*"([^"]+)"'),
]

_BLOGGER_TOKEN_RE = re.compile(r'blogger\.com/video\.g\?token=')


class _VideoSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "source":
            src = attrs_dict.get("src", "")
            if src:
                self.sources.append(src)
        elif tag == "video":
            src = attrs_dict.get("src", "")
            if src:
                self.sources.append(src)
            poster = attrs_dict.get("poster", "")

    def handle_data(self, data):
        pass


def _is_blogger_url(url: str) -> bool:
    return bool(_BLOGGER_TOKEN_RE.search(url))


async def resolve_blogger_url(
    blogger_url: str,
    session: aiohttp.ClientSession,
) -> str | None:
    if not _is_blogger_url(blogger_url):
        return blogger_url

    html = await _fetch_blogger_page(blogger_url, session)
    if not html:
        return None

    resolved = _extract_url_regex(html)
    if resolved:
        logger.debug(f"Regex resolve OK: {resolved[:80]}...")
        return resolved

    resolved = _extract_url_parser(html)
    if resolved:
        logger.debug(f"Parser resolve OK: {resolved[:80]}...")
        return resolved

    logger.warning(f"Nao resolveu URL do Blogger: {blogger_url[:80]}...")
    return None


async def _fetch_blogger_page(
    url: str,
    session: aiohttp.ClientSession,
) -> str | None:
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=BLOGGER_TIMEOUT),
            allow_redirects=True,
            ssl=False,
        ) as resp:
            if resp.status != 200:
                logger.warning(f"Blogger HTTP {resp.status} para {url[:80]}")
                return None
            return await resp.text()
    except asyncio.TimeoutError:
        logger.warning(f"Blogger timeout para {url[:80]}")
        return None
    except Exception as e:
        logger.error(f"Blogger erro para {url[:80]}: {e}")
        return None


def _extract_url_regex(html: str) -> str | None:
    for pattern in _REGEX_PATTERNS:
        match = pattern.search(html)
        if match:
            url = match.group(1)
            if url.startswith("//"):
                url = "https:" + url
            return url
    return None


def _extract_url_parser(html: str) -> str | None:
    parser = _VideoSourceParser()
    try:
        parser.feed(html)
    except Exception:
        return None

    for url in parser.sources:
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http"):
            return url

    return None


import asyncio
