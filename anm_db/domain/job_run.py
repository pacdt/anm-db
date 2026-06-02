"""Entidade JobRun (historico de execucoes dos cronjobs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


JobStatus = Literal["running", "success", "error", "skipped"]


@dataclass(frozen=True, slots=True)
class JobRun:
    id: int
    job_id: str
    started_at: str
    finished_at: str | None = None
    status: str | None = None
    animes_checked: int = 0
    eps_novos: int = 0
    cdn_hits: int = 0
    af_fallbacks: int = 0
    erro_msg: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any] | Any) -> "JobRun":
        d = dict(row) if not isinstance(row, dict) else row
        return cls(
            id=d["id"],
            job_id=d["job_id"],
            started_at=d["started_at"],
            finished_at=d.get("finished_at"),
            status=d.get("status"),
            animes_checked=d.get("animes_checked") or 0,
            eps_novos=d.get("eps_novos") or 0,
            cdn_hits=d.get("cdn_hits") or 0,
            af_fallbacks=d.get("af_fallbacks") or 0,
            erro_msg=d.get("erro_msg"),
        )

    @property
    def duration_seconds(self) -> float | None:
        if not self.finished_at:
            return None
        from datetime import datetime
        try:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.finished_at)
            return (end - start).total_seconds()
        except (ValueError, TypeError):
            return None
