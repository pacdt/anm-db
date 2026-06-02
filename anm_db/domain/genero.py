"""Entidade Genero."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Genero:
    id: int
    nome: str                # original (geralmente EN do Jikan)
    nome_pt: str | None = None
    count: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "Genero":
        d = dict(row) if not isinstance(row, dict) else row
        return cls(
            id=d["id"],
            nome=d["nome"],
            nome_pt=d.get("nome_pt") or d.get("nome"),
            count=d.get("count", 0),
        )

    @property
    def display_nome(self) -> str:
        return self.nome_pt or self.nome
