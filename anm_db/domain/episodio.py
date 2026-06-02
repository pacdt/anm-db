"""Entidade Episodio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Episodio:
    id: int
    anime_id: int
    numero: int
    titulo: str | None = None
    titulo_pt: str | None = None
    url_cdn: str | None = None
    url_af: str | None = None
    fonte_ativa: str = "cdn"
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "Episodio":
        d = dict(row) if not isinstance(row, dict) else row
        return cls(
            id=d["id"],
            anime_id=d["anime_id"],
            numero=d["numero"],
            titulo=d.get("titulo"),
            titulo_pt=d.get("titulo_pt"),
            url_cdn=d.get("url_cdn"),
            url_af=d.get("url_af"),
            fonte_ativa=d.get("fonte_ativa") or "cdn",
            created_at=d.get("created_at"),
        )

    def available_sources(self) -> list[str]:
        sources = []
        if self.url_cdn:
            sources.append("cdn")
        if self.url_af:
            sources.append("animefire")
        return sources

    def display_titulo(self, lang: str = "pt-BR") -> str | None:
        if lang == "pt-BR":
            return self.titulo_pt or self.titulo
        return self.titulo
