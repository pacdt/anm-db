"""Entidade SkipTime (intro/ending de episodio)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SkipType = Literal["op", "ed"]


@dataclass(frozen=True, slots=True)
class SkipTime:
    id: int
    anime_id: int
    ep_numero: int
    tipo: SkipType
    start_time: float
    end_time: float

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "SkipTime":
        d = dict(row) if not isinstance(row, dict) else row
        return cls(
            id=d["id"],
            anime_id=d["anime_id"],
            ep_numero=d["ep_numero"],
            tipo=d["tipo"],
            start_time=d["start_time"],
            end_time=d["end_time"],
        )

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)
