"""Shim de retrocompatibilidade. Use anm_db.api.schemas ao inves deste."""

from anm_db.api.schemas import (
    AnimeDetail,
    AnimeSummary,
    EpisodeOut,
    GeneroOut,
    PaginatedResponse,
    pick_lang,
)

__all__ = [
    "AnimeDetail",
    "AnimeSummary",
    "EpisodeOut",
    "GeneroOut",
    "PaginatedResponse",
    "pick_lang",
]
