"""
Scheduler do anm-db.

Jobs cron:
- 03:00 (domingo)    missing_scan_translate: varre animes faltantes + traduz PT-BR
- 06:00 (diario)     jikan_sync: sincroniza catalogo Jikan
- 07:00 (diario)     episode_scan: busca novos episodios dos animes ongoing
- 08:00 (diario)     backfill_skip_times: preenche skip times do Aniskip
"""

from anm_db.scheduler.jobs import (
    backfill_skip_times_job,
    create_scheduler,
    missing_scan_translate_job,
    scan_ongoing_episodes,
    sync_jikan_job,
)

__all__ = [
    "create_scheduler",
    "sync_jikan_job",
    "scan_ongoing_episodes",
    "backfill_skip_times_job",
    "missing_scan_translate_job",
]
