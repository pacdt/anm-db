"""
Servico de deteccao de animes faltantes/incompletos.

Tres estrategias:
1. Animes com 0 episodios salvos
2. Animes com gap (episodes_aired do Jikan > ultimo_ep_salvo)
3. Animes finalizados sem varredura ha mais de N dias

Re-executa o scraper AnimeScraper.atualizar_anime() para tentar preencher
os dados faltantes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from anm_db.config import get_settings
from anm_db.repository.database import DatabaseManager
from anm_db.scrapers.animefire import AnimeScraper

logger = logging.getLogger("MissingScanner")


@dataclass
class MissingScanReport:
    without_eps: int = 0
    with_gaps: int = 0
    stale_finished: int = 0
    total_scanned: int = 0
    eps_added: int = 0
    cdn_hits: int = 0
    af_fallbacks: int = 0

    def to_dict(self) -> dict:
        return {
            "without_eps": self.without_eps,
            "with_gaps": self.with_gaps,
            "stale_finished": self.stale_finished,
            "total_scanned": self.total_scanned,
            "eps_added": self.eps_added,
            "cdn_hits": self.cdn_hits,
            "af_fallbacks": self.af_fallbacks,
        }


class MissingEpisodeScanner:
    def __init__(self, db: DatabaseManager, scraper: AnimeScraper | None = None):
        self.db = db
        self.scraper = scraper
        self.stale_days = 14

    async def scan(self, limit: int = 100, limit_per_category: int | None = None) -> MissingScanReport:
        """Executa varredura completa de animes faltantes/incompletos.
        Aceita tanto `limit` (limite global) quanto `limit_per_category` (legado).
        """
        if limit_per_category is None:
            limit_per_category = limit
        """Executa varredura completa de animes faltantes/incompletos."""
        report = MissingScanReport()

        sem_eps = await self.db.list_animes_without_episodes(limit=limit_per_category)
        report.without_eps = len(sem_eps)
        logger.info(f"Missing scan: {len(sem_eps)} animes sem episodios")

        with_gaps = await self.db.list_animes_with_gaps(limit=limit_per_category)
        report.with_gaps = len(with_gaps)
        logger.info(f"Missing scan: {len(with_gaps)} animes com gaps")

        stale = await self.db.list_finished_stale_animes(
            days=self.stale_days, limit=limit_per_category
        )
        report.stale_finished = len(stale)
        logger.info(
            f"Missing scan: {len(stale)} animes finalizados sem varredura "
            f"ha >{self.stale_days}d"
        )

        all_animes = sem_eps + with_gaps + stale
        report.total_scanned = len(all_animes)

        if not all_animes:
            return report

        if self.scraper is None:
            self.scraper = AnimeScraper(self.db)
            await self.scraper.start_session()
            owns_scraper = True
        else:
            owns_scraper = False

        try:
            for anime in all_animes:
                try:
                    novos_eps, _is_new, cdn_hits, af_fallbacks = (
                        await self.scraper.atualizar_anime(anime, anime.get("tipo", "legendado"))
                    )
                    report.eps_added += novos_eps
                    report.cdn_hits += cdn_hits
                    report.af_fallbacks += af_fallbacks
                except Exception as e:
                    logger.error(
                        f"Erro ao re-varrer {anime.get('slug')}: {e}"
                    )
        finally:
            if owns_scraper:
                await self.scraper.close_session()

        return report
