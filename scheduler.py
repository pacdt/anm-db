import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db import DatabaseManager
from jikan import JikanSync

logger = logging.getLogger("Scheduler")


async def sync_jikan_job():
    logger.info("jikan_sync iniciado")
    run_id = None
    try:
        db = DatabaseManager()
        await db.init_db()
        run_id = await db.log_job_start("jikan_sync")

        syncer = JikanSync(db)
        await syncer.sync_jikan_catalog()

        await db.log_job_end(run_id, "success")
        logger.info("jikan_sync concluido com sucesso")
        await db.close()
    except Exception as e:
        logger.error(f"jikan_sync falhou: {e}")
        if run_id and db:
            await db.log_job_end(run_id, "error", erro_msg=str(e))
            await db.close()


async def scan_ongoing_episodes():
    logger.info("episode_scan iniciado")
    run_id = None
    db = None
    try:
        db = DatabaseManager()
        await db.init_db()
        run_id = await db.log_job_start("episode_scan")

        animes = await db.get_ongoing_due()
        logger.info(f"{len(animes)} animes na fila")

        if not animes:
            await db.log_job_end(run_id, "success", animes_checked=0)
            await db.close()
            return

        from script import AnimeScraper
        scraper = AnimeScraper(db)
        await scraper.start_session()

        total_eps = 0
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
        await db.log_job_end(
            run_id, "success",
            animes_checked=len(animes),
            eps_novos=total_eps,
            cdn_hits=total_cdn,
            af_fallbacks=total_af,
        )
        logger.info(
            f"episode_scan concluido: {len(animes)} animes, "
            f"{total_eps} eps (CDN: {total_cdn}, AF: {total_af})"
        )
        await db.close()
    except Exception as e:
        logger.error(f"episode_scan falhou: {e}")
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

    return scheduler
