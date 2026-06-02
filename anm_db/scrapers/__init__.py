"""Scrapers (external data sources): Jikan, CDN, Animefire, Aniskip, Blogger, Gemini."""

from anm_db.scrapers.jikan import JikanSync
from anm_db.scrapers.cdn import (
    CDN_DOMAINS,
    build_url,
    check_cdn_episode,
    format_ep,
    head_request,
)
from anm_db.scrapers.aniskip import fetch_and_save_skip_times, fetch_skip_times
from anm_db.scrapers.animefire import AnimeScraper
from anm_db.scrapers.blogger import resolve_blogger_url
from anm_db.scrapers.gemini import GeminiClient
from anm_db.scrapers.genre_translator import (
    GENRE_PT_MAP,
    THEME_PT_MAP,
    translate_genre,
)

__all__ = [
    "JikanSync",
    "CDN_DOMAINS",
    "build_url",
    "check_cdn_episode",
    "format_ep",
    "head_request",
    "fetch_and_save_skip_times",
    "fetch_skip_times",
    "AnimeScraper",
    "resolve_blogger_url",
    "GeminiClient",
    "GENRE_PT_MAP",
    "THEME_PT_MAP",
    "translate_genre",
]
