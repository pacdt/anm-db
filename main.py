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
        choices=["full", "ongoing", "jikan-sync", "migrate", "api", "scheduler"],
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
                from script import BASE_URL_SITE

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


if __name__ == "__main__":
    main()
