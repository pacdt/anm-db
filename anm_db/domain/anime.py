"""Entidade Anime (mapeamento 1:1 com tabela `animes`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Anime:
    id: int
    slug: str
    tipo: str
    mal_id: int | None = None
    titulo: str | None = None
    titulo_en: str | None = None
    titulo_jp: str | None = None
    titulo_pt: str | None = None
    imagem: str | None = None
    score: float | None = None
    sinopse: str | None = None
    sinopse_pt: str | None = None
    trailer_url: str | None = None
    status: str | None = None
    next_check_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    traduzido_em: str | None = None
    traducao_modelo: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "Anime":
        """Constroi a partir de uma linha do banco (aiosqlite.Row ou dict)."""
        d = dict(row) if not isinstance(row, dict) else row
        return cls(
            id=d["id"],
            slug=d["slug"],
            tipo=d["tipo"],
            mal_id=d.get("mal_id"),
            titulo=d.get("titulo"),
            titulo_en=d.get("titulo_en"),
            titulo_jp=d.get("titulo_jp"),
            titulo_pt=d.get("titulo_pt"),
            imagem=d.get("imagem"),
            score=d.get("score"),
            sinopse=d.get("sinopse"),
            sinopse_pt=d.get("sinopse_pt"),
            trailer_url=d.get("trailer_url"),
            status=d.get("status"),
            next_check_at=d.get("next_check_at"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            traduzido_em=d.get("traduzido_em"),
            traducao_modelo=d.get("traducao_modelo"),
        )

    @property
    def is_translated(self) -> bool:
        return self.sinopse_pt is not None or self.titulo_pt is not None

    @property
    def is_ongoing(self) -> bool:
        return self.status == "ongoing"

    @property
    def display_title(self, lang: str = "pt-BR") -> str | None:
        if lang == "pt-BR":
            return self.titulo_pt or self.titulo_en or self.titulo
        if lang == "en":
            return self.titulo_en or self.titulo
        if lang == "jp":
            return self.titulo_jp
        return self.titulo
