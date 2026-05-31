import os
import sys
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Main")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="anm-db")
    parser.add_argument(
        "--mode",
        choices=["full", "ongoing", "jikan-sync", "migrate", "api", "scheduler",
                 "backfill-skip-times"],
        default="full",
        help="Modo de execucao",
    )
    args = parser.parse_args()

    if args.mode == "migrate":
        from migrate import main as migrate_main
        asyncio.run(migrate_main())
        return

    if args.mode == "api":
        import uvicorn
        uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
        return

    if args.mode == "scheduler":
        from scheduler import create_scheduler
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("Scheduler iniciado. Pressione Ctrl+C para parar.")
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
        return

    if args.mode == "backfill-skip-times":
        asyncio.run(_backfill_skip_times())
        return

    # Full, ongoing, jikan-sync modes
    from db import DatabaseManager

    async def run():
        db = DatabaseManager()
        await db.init_db()

        if args.mode == "jikan-sync":
            from jikan import JikanSync
            syncer = JikanSync(db)
            await syncer.sync_jikan_catalog()
            await db.close()
            return

        from script import AnimeScraper

        scraper = AnimeScraper(db)
        await scraper.start_session()

        try:
            if args.mode == "full":
                logger.info("Mapeando catalogos...")
                dub = await scraper.mapear_catalogo("dublado", 32)
                leg = await scraper.mapear_catalogo("legendado", 200)

                logger.info("Processando episodios...")
                await scraper.processar_lista(dub, "dublado")
                await scraper.processar_lista(leg, "legendado")

            elif args.mode == "ongoing":
                animes = await db.get_ongoing_due()
                logger.info(f"{len(animes)} animes na fila")

                for anime in animes:
                    await scraper.atualizar_anime(anime, anime["tipo"])

                await db.reschedule_next_check(
                    [a["id"] for a in animes], hours=24
                )

        finally:
            await scraper.close_session()
            await db.close()

    asyncio.run(run())


async def _backfill_skip_times():
    from db import DatabaseManager
    from aniskip import fetch_skip_times
    import aiohttp

    db = DatabaseManager()
    await db.init_db()

    async with db._db.execute("""
        SELECT a.id, a.mal_id, a.slug, e.numero
        FROM animes a
        JOIN episodios e ON a.id = e.anime_id
        WHERE a.mal_id IS NOT NULL
        ORDER BY a.slug, e.numero
    """) as cur:
        rows = await cur.fetchall()

    logger.info(f"Encontrados {len(rows)} episodios com mal_id para backfill")

    skip_count = 0
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

            if (i + 1) % 50 == 0:
                logger.info(f"Progresso: {i + 1}/{len(rows)} episodios, {skip_count} skip times salvos")

            await asyncio.sleep(0.5)

    await db.close()
    logger.info(f"Backfill concluido: {skip_count} skip times salvos")


if __name__ == "__main__":
    main()
