"""Entidade TranslationLog (auditoria de chamadas Gemini)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TranslationStatus = Literal["success", "error", "skipped_quota", "skipped_no_key"]


@dataclass(frozen=True, slots=True)
class TranslationLog:
    id: int
    anime_id: int
    provider: str
    status: str
    started_at: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finished_at: str | None = None
    erro_msg: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "TranslationLog":
        d = dict(row) if not isinstance(row, dict) else row
        return cls(
            id=d["id"],
            anime_id=d["anime_id"],
            provider=d["provider"],
            status=d["status"],
            started_at=d["started_at"],
            input_tokens=d.get("input_tokens"),
            output_tokens=d.get("output_tokens"),
            finished_at=d.get("finished_at"),
            erro_msg=d.get("erro_msg"),
        )

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)
