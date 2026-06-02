"""Entidade JikanMetadata (clone normalizado do payload Jikan)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class JikanMetadata:
    """Snapshot normalizado do payload /anime/{mal_id} do Jikan.

    Listas (studios, producers, themes, relations, etc.) sao armazenadas como
    JSON strings no banco (colunas *_json). Esta entidade expoe como listas.
    """

    anime_id: int
    mal_id: int
    jikan_fetched_at: str
    jikan_updated_at: str

    url: str | None = None
    approved: bool | None = None
    title_japanese: str | None = None
    title_romaji: str | None = None
    type: str | None = None
    source: str | None = None
    episodes_total: int | None = None
    episodes_aired: int | None = None
    status_jikan: str | None = None
    airing: bool | None = None
    aired_from: str | None = None
    aired_to: str | None = None
    duration: str | None = None
    rating: str | None = None
    season: str | None = None
    year: int | None = None
    broadcast_day: str | None = None
    broadcast_time: str | None = None

    studios: list[str] = field(default_factory=list)
    producers: list[str] = field(default_factory=list)
    licensors: list[str] = field(default_factory=list)
    demographics: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    external_links: list[dict] = field(default_factory=list)
    streaming: list[dict] = field(default_factory=list)
