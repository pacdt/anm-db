"""
Entry point CLI do anm-db.

Modos disponiveis:
- full:             scraping completo (catalogo dublado + legendado)
- ongoing:          scrape incremental de animes ongoing
- jikan-sync:       sincroniza catalogo Jikan (metadata completa)
- migrate:          aplica migracoes do schema
- api:              inicia servidor FastAPI
- scheduler:        inicia APScheduler com todos os jobs
- backfill-skip-times:  preenche skip times do Aniskip
- translate:        traduz titulo+sinopse PT-BR via Gemini
- missing-scan:     detecta animes com episodios faltantes
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

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
        choices=[
            "full", "ongoing", "jikan-sync", "migrate", "api", "scheduler",
            "backfill-skip-times", "translate", "missing-scan",
        ],
        default="full",
        help="Modo de execucao",
    )
    parser.add_argument(
        "--skip-if-recent",
        type=int,
        default=None,
        help="Pular modo se ultimo success < N horas atras",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite de animes a processar (translate/missing-scan)",
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

    if args.mode == "translate":
        asyncio.run(_translate_mode(args))
        return

    if args.mode == "missing-scan":
        asyncio.run(_missing_scan_mode(args))
        return

    if args.mode == "backfill-skip-times":
        asyncio.run(_backfill_skip_times(args))
        return

    asyncio.run(_scraper_mode(args))


async def _translate_mode(args):
    """Traduz titulo + sinopse PT-BR via Gemini."""
    from db import DatabaseManager
    from anm_db.config import get_settings
    from anm_db.scrapers.gemini import GeminiClient
    from anm_db.services.translator import AnimeTranslator

    settings = get_settings()
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY nao configurada no .env")
        return

    db = DatabaseManager()
    await db.init_db()
    client = GeminiClient(api_key=settings.gemini_api_key)
    if not client.available:
        logger.error("GeminiClient nao inicializou (chave invalida?)")
        await db.close()
        return

    translator = AnimeTranslator(db, client)
    report = await translator.translate_pending(
        batch_size=settings.translation_batch_size,
        limit=args.limit,
    )
    logger.info(f"Traducao concluida: {report.to_dict()}")
    await db.close()


async def _missing_scan_mode(args):
    """Detecta animes com episodios faltantes."""
    from db import DatabaseManager
    from anm_db.services.missing_scanner import MissingEpisodeScanner

    db = DatabaseManager()
    await db.init_db()
    scanner = MissingEpisodeScanner(db)
    report = await scanner.scan(limit=args.limit or 200)
    logger.info(f"Missing scan concluido: {report.to_dict()}")
    await db.close()


async def _backfill_skip_times(args):
    from db import DatabaseManager
    from aniskip import fetch_skip_times
    import aiohttp

    if args.skip_if_recent:
        db = DatabaseManager()
        await db.init_db()
        last = await db.get_last_successful_run("backfill_skip_times")
        await db.close()
        if last:
            elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last)
            if elapsed.total_seconds() < args.skip_if_recent * 3600:
                logger.info(
                    f"Pulando backfill_skip_times (rodou "
                    f"{elapsed.total_seconds() / 3600:.1f}h atras)"
                )
                return

    db = DatabaseManager()
    await db.init_db()
    try:
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
                    logger.info(
                        f"Progresso: {i + 1}/{len(rows)} episodios, "
                        f"{skip_count} skip times salvos"
                    )
                await asyncio.sleep(0.5)
    finally:
        await db.close()

    logger.info(f"Backfill concluido: {skip_count} skip times salvos")


async def _scraper_mode(args):
    """Modos: full, ongoing, jikan-sync."""
    from db import DatabaseManager

    async def run():
        db = DatabaseManager()
        await db.init_db()

        if args.mode == "jikan-sync":
            if args.skip_if_recent:
                last = await db.get_last_successful_run("jikan_sync")
                if last:
                    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last)
                    if elapsed.total_seconds() < args.skip_if_recent * 3600:
                        logger.info(
                            f"Pulando jikan_sync "
                            f"(rodou {elapsed.total_seconds() / 3600:.1f}h atras)"
                        )
                        await db.close()
                        return
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


if __name__ == "__main__":
    main()
