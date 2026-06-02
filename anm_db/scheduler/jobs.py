"""
Jobs do scheduler do anm-db.

Cada job:
- abre conexao com DB
- loga inicio via db.log_job_start
- executa trabalho
- loga fim com status (success/error) via db.log_job_end
- fecha conexao

Em caso de excecao, o job e registrado como 'error' com mensagem.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from anm_db.repository.database import DatabaseManager

logger = logging.getLogger("Scheduler")


# ============================================================================
# Helpers
# ============================================================================

async def _run_job(job_name: str, coro_factory):
    """Wrapper padrao: log + try/except + close."""
    start = time.monotonic()
    logger.info(f"[{job_name}] iniciado")
    run_id = None
    db: DatabaseManager | None = None
    try:
        db = DatabaseManager()
        await db.init_db()
        run_id = await db.log_job_start(job_name)

        result = await coro_factory(db)

        elapsed = time.monotonic() - start
        mins, secs = int(elapsed // 60), int(elapsed % 60)

        # result pode ser um dict com metricas opcionais
        kwargs = {}
        if isinstance(result, dict):
            for k in (
                "animes_checked", "eps_novos",
                "cdn_hits", "af_fallbacks", "translated", "failed",
            ):
                if k in result:
                    kwargs[k] = result[k]
        await db.log_job_end(run_id, "success", **kwargs)
        logger.info(
            f"[{job_name}] concluido em {mins}m {secs}s"
            + (f" — metricas: {kwargs}" if kwargs else "")
        )
        await db.close()
    except Exception as e:
        elapsed = time.monotonic() - start
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        logger.error(f"[{job_name}] falhou em {mins}m {secs}s: {e}")
        if run_id and db:
            try:
                await db.log_job_end(run_id, "error", erro_msg=str(e))
            except Exception:
                pass


# ============================================================================
# Job: jikan_sync (06:00 diario)
# ============================================================================

async def sync_jikan_job():
    async def work(db: DatabaseManager):
        from anm_db.scrapers.jikan import JikanSync
        syncer = JikanSync(db)
        await syncer.sync_jikan_catalog()
        return {}
    await _run_job("jikan_sync", work)


# ============================================================================
# Job: episode_scan (07:00 diario)
# ============================================================================

async def scan_ongoing_episodes():
    async def work(db: DatabaseManager):
        animes = await db.get_ongoing_due()
        logger.info(f"[episode_scan] {len(animes)} animes na fila")
        if not animes:
            return {"animes_checked": 0, "eps_novos": 0}

        from anm_db.scrapers.animefire import AnimeScraper
        scraper = AnimeScraper(db)
        await scraper.start_session()
        try:
            total_cdn = 0
            total_af = 0

            async def process(anime):
                _, _, cdn, af = await scraper.atualizar_anime(anime, anime["tipo"])
                return cdn, af

            results = await asyncio.gather(
                *[process(a) for a in animes], return_exceptions=True
            )
            for r in results:
                if isinstance(r, tuple):
                    total_cdn += r[0]
                    total_af += r[1]

            total_eps = total_cdn + total_af
            await db.reschedule_next_check([a["id"] for a in animes], hours=24)

            return {
                "animes_checked": len(animes),
                "eps_novos": total_eps,
                "cdn_hits": total_cdn,
                "af_fallbacks": total_af,
            }
        finally:
            await scraper.close_session()
    await _run_job("episode_scan", work)


# ============================================================================
# Job: backfill_skip_times (08:00 diario)
# ============================================================================

async def backfill_skip_times_job():
    async def work(db: DatabaseManager):
        from anm_db.scrapers.aniskip import fetch_skip_times

        async with db._db.execute("""
            SELECT a.id, a.mal_id, a.slug, e.numero
            FROM animes a
            JOIN episodios e ON a.id = e.anime_id
            WHERE a.mal_id IS NOT NULL
            ORDER BY a.slug, e.numero
        """) as cur:
            rows = await cur.fetchall()

        logger.info(f"[backfill_skip_times] {len(rows)} episodios com mal_id")
        skip_count = 0
        processed = 0
        async with aiohttp.ClientSession() as session:
            for i, (anime_id, mal_id, slug, ep_numero) in enumerate(rows):
                existing = await db.get_skip_times(anime_id, ep_numero)
                if existing:
                    continue
                skip_times = await fetch_skip_times(mal_id, ep_numero, session=session)
                for skip_type, times in skip_times.items():
                    await db.upsert_skip_time(
                        anime_id=anime_id,
                        ep_numero=ep_numero,
                        tipo=skip_type,
                        start_time=times["start"],
                        end_time=times["end"],
                    )
                    skip_count += 1
                processed += 1
                if processed % 50 == 0:
                    logger.info(
                        f"[backfill_skip_times] {processed}/{len(rows)} eps, "
                        f"{skip_count} skip times"
                    )
                await asyncio.sleep(0.5)

        return {"eps_novos": processed}
    await _run_job("backfill_skip_times", work)


# ============================================================================
# Job: missing_scan_translate (03:00 domingo)
# ============================================================================

async def missing_scan_translate_job():
    """Combina varredura de episodios faltantes + traducao PT-BR.

    Ordem:
    1. Missing scan: detecta animes sem eps, com gaps, ou stale
    2. Re-executa scraper nesses animes para tentar preencher
    3. Translator: traduz titulo + sinopse dos animes pendentes
    """
    async def work(db: DatabaseManager):
        result = {}

        # 1. Missing scan
        logger.info("[missing_scan_translate] iniciando missing scan")
        from anm_db.services.missing_scanner import MissingEpisodeScanner
        scanner = MissingEpisodeScanner(db)
        scan_report = await scanner.scan(limit=200)
        result["animes_checked"] = scan_report.total_scanned
        result["cdn_hits"] = scan_report.cdn_hits
        result["af_fallbacks"] = scan_report.af_fallbacks
        logger.info(
            f"[missing_scan_translate] scan: "
            f"{scan_report.without_eps} sem eps, "
            f"{scan_report.with_gaps} com gaps, "
            f"{scan_report.stale_finished} stale, "
            f"{scan_report.eps_added} eps adicionados"
        )

        # 2. Translator (so roda se Gemini configurado)
        from anm_db.config import get_settings
        settings = get_settings()
        if settings.gemini_api_key and settings.translation_enabled:
            logger.info("[missing_scan_translate] iniciando traducao PT-BR")
            from anm_db.scrapers.gemini import GeminiClient
            from anm_db.services.translator import AnimeTranslator

            client = GeminiClient(api_key=settings.gemini_api_key)
            if client.available:
                translator = AnimeTranslator(db, client)
                trans_report = await translator.translate_pending(
                    batch_size=settings.translation_batch_size,
                )
                result["translated"] = trans_report.translated
                result["failed"] = trans_report.failed
                logger.info(
                    f"[missing_scan_translate] traducao: "
                    f"{trans_report.translated} traduzidos, "
                    f"{trans_report.failed} falhas, "
                    f"{trans_report.skipped} pulados"
                )
            else:
                logger.warning(
                    "[missing_scan_translate] GeminiClient nao disponivel, pulando"
                )
        else:
            logger.info(
                "[missing_scan_translate] traducao desabilitada (sem API key ou flag off)"
            )

        return result

    await _run_job("missing_scan_translate", work)


# ============================================================================
# create_scheduler
# ============================================================================

def create_scheduler() -> AsyncIOScheduler:
    """Cria scheduler com todos os jobs configurados."""
    scheduler = AsyncIOScheduler()

    # Traducao + missing scan: 03:00 UTC todo domingo
    scheduler.add_job(
        missing_scan_translate_job,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="missing_scan_translate",
        name="Missing scan + traducao PT-BR",
    )

    # Jikan sync: 06:00 UTC diario
    scheduler.add_job(
        sync_jikan_job,
        CronTrigger(hour=6, minute=0),
        id="jikan_sync",
        name="Sincronizacao Jikan",
    )

    # Episode scan: 07:00 UTC diario
    scheduler.add_job(
        scan_ongoing_episodes,
        CronTrigger(hour=7, minute=0),
        id="episode_scan",
        name="Varredura de episodios",
    )

    # Backfill skip times: 08:00 UTC diario
    scheduler.add_job(
        backfill_skip_times_job,
        CronTrigger(hour=8, minute=0),
        id="backfill_skip_times",
        name="Backfill skip times",
    )

    return scheduler
