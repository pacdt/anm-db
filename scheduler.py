import time
import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db import DatabaseManager
from jikan import JikanSync

logger = logging.getLogger("Scheduler")


async def sync_jikan_job():
    start = time.monotonic()
    logger.info("[06:00:00] jikan_sync iniciado")
    run_id = None
    db = None
    try:
        db = DatabaseManager()
        await db.init_db()
        run_id = await db.log_job_start("jikan_sync")

        syncer = JikanSync(db)
        await syncer.sync_jikan_catalog()

        elapsed = time.monotonic() - start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        await db.log_job_end(run_id, "success")
        logger.info(
            f"[06:00:00] jikan_sync concluido com sucesso — "
            f"Tempo: {mins}m {secs}s"
        )
        await db.close()
    except Exception as e:
        elapsed = time.monotonic() - start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        logger.error(f"[06:00:00] jikan_sync falhou: {e} — Tempo: {mins}m {secs}s")
        if run_id and db:
            await db.log_job_end(run_id, "error", erro_msg=str(e))
            await db.close()


async def scan_ongoing_episodes():
    start = time.monotonic()
    logger.info("[07:00:00] episode_scan iniciado")
    run_id = None
    db = None
    try:
        db = DatabaseManager()
        await db.init_db()
        run_id = await db.log_job_start("episode_scan")

        animes = await db.get_ongoing_due()
        logger.info(f"[07:00:01] {len(animes)} animes na fila")

        if not animes:
            await db.log_job_end(run_id, "success", animes_checked=0)
            logger.info("[07:00:01] episode_scan concluido — 0 animes na fila")
            await db.close()
            return

        from script import AnimeScraper
        scraper = AnimeScraper(db)
        await scraper.start_session()

        total_cdn = 0
        total_af = 0

        async def process_anime(anime):
            _, _, cdn, af = await scraper.atualizar_anime(anime, anime["tipo"])
            return cdn, af

        import asyncio
        results = await asyncio.gather(
            *[process_anime(a) for a in animes],
            return_exceptions=True,
        )

        for r in results:
            if isinstance(r, tuple):
                total_cdn += r[0]
                total_af += r[1]

        total_eps = total_cdn + total_af
        await db.reschedule_next_check([a["id"] for a in animes], hours=24)

        await scraper.close_session()

        elapsed = time.monotonic() - start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        total_all = total_cdn + total_af
        cdn_pct = (total_cdn / total_all * 100) if total_all > 0 else 0
        af_pct = (total_af / total_all * 100) if total_all > 0 else 0

        await db.log_job_end(
            run_id, "success",
            animes_checked=len(animes),
            eps_novos=total_eps,
            cdn_hits=total_cdn,
            af_fallbacks=total_af,
        )
        logger.info(
            f"[07:00:01] episode_scan concluido — "
            f"Animes verificados: {len(animes)} | "
            f"Episodios novos: {total_eps} | "
            f"CDN hits: {total_cdn} ({cdn_pct:.0f}%) | "
            f"AF fallbacks: {total_af} ({af_pct:.0f}%) | "
            f"Tempo: {mins}m {secs}s"
        )
        await db.close()
    except Exception as e:
        elapsed = time.monotonic() - start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        logger.error(f"[07:00:00] episode_scan falhou: {e} — Tempo: {mins}m {secs}s")
        if run_id and db:
            await db.log_job_end(run_id, "error", erro_msg=str(e))
            await db.close()


async def backfill_skip_times_job():
    start = time.monotonic()
    logger.info("[08:00:00] backfill_skip_times iniciado")
    run_id = None
    db = None
    try:
        db = DatabaseManager()
        await db.init_db()
        run_id = await db.log_job_start("backfill_skip_times")

        from aniskip import fetch_skip_times
        import aiohttp

        async with db._db.execute("""
            SELECT a.id, a.mal_id, a.slug, e.numero
            FROM animes a
            JOIN episodios e ON a.id = e.anime_id
            WHERE a.mal_id IS NOT NULL
            ORDER BY a.slug, e.numero
        """) as cur:
            rows = await cur.fetchall()

        logger.info(f"[08:00:01] {len(rows)} episodios com mal_id para backfill")

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
                    logger.info(f"[08:00:01] Progresso: {processed}/{len(rows)} eps, {skip_count} skip times")

                await asyncio.sleep(0.5)

        elapsed = time.monotonic() - start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        await db.log_job_end(
            run_id, "success",
            eps_novos=processed,
        )
        logger.info(
            f"[08:00:00] backfill_skip_times concluido — "
            f"Episodios processados: {processed} | "
            f"Skip times salvos: {skip_count} | "
            f"Tempo: {mins}m {secs}s"
        )
        await db.close()
    except Exception as e:
        elapsed = time.monotonic() - start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        logger.error(f"[08:00:00] backfill_skip_times falhou: {e} — Tempo: {mins}m {secs}s")
        if run_id and db:
            await db.log_job_end(run_id, "error", erro_msg=str(e))
            await db.close()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        sync_jikan_job,
        CronTrigger(hour=6, minute=0),
        id="jikan_sync",
        name="Sincronizacao Jikan",
    )

    scheduler.add_job(
        scan_ongoing_episodes,
        CronTrigger(hour=7, minute=0),
        id="episode_scan",
        name="Varredura de episodios",
    )

    scheduler.add_job(
        backfill_skip_times_job,
        CronTrigger(hour=8, minute=0),
        id="backfill_skip_times",
        name="Backfill skip times",
    )

    return scheduler
