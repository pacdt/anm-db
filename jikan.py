import asyncio
import logging
import aiohttp

logger = logging.getLogger("Jikan")

JIKAN_BASE = "https://api.jikan.moe/v4/anime"
JIKAN_RATE_LIMIT = 3
JIKAN_TIMEOUT = 10
JIKAN_MAX_RETRIES = 3
JIKAN_RETRY_DELAY = 60


class JikanSync:
    def __init__(self, db):
        self.db = db
        self.semaphore = asyncio.Semaphore(JIKAN_RATE_LIMIT)
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=JIKAN_TIMEOUT)
        )

    async def close(self):
        if self.session:
            await self.session.close()

    async def _fetch_page(self, page: int) -> dict | None:
        async with self.semaphore:
            for attempt in range(JIKAN_MAX_RETRIES):
                try:
                    async with self.session.get(
                        JIKAN_BASE,
                        params={
                            "status": "airing",
                            "order_by": "score",
                            "sort": "desc",
                            "page": page,
                        },
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status in (429, 503):
                            logger.warning(
                                f"Jikan {resp.status} na pagina {page}. "
                                f"Tentativa {attempt + 1}/{JIKAN_MAX_RETRIES}. "
                                f"Aguardando {JIKAN_RETRY_DELAY}s..."
                            )
                            await asyncio.sleep(JIKAN_RETRY_DELAY)
                        else:
                            logger.error(f"Jikan erro {resp.status} na pagina {page}")
                            return None
                except Exception as e:
                    logger.error(f"Jikan excecao na pagina {page}: {e}")
                    if attempt < JIKAN_MAX_RETRIES - 1:
                        await asyncio.sleep(JIKAN_RETRY_DELAY)
            return None

    async def fetch_all_airing(self) -> list[dict]:
        all_animes = []
        page = 1
        last_page = 1

        while page <= last_page:
            data = await self._fetch_page(page)
            if not data:
                break

            last_page = data.get("pagination", {}).get("last_visible_page", 1)
            items = data.get("data", [])
            all_animes.extend(items)
            logger.info(f"Jikan pagina {page}/{last_page}: {len(items)} animes")
            page += 1

            await asyncio.sleep(1)

        logger.info(f"Jikan total: {len(all_animes)} animes airing")
        return all_animes

    def _extract_anime_data(self, jikan_anime: dict) -> dict:
        trailer = jikan_anime.get("trailer") or {}
        return {
            "mal_id": jikan_anime.get("mal_id"),
            "titulo": jikan_anime.get("title"),
            "titulo_en": jikan_anime.get("title_english"),
            "titulo_jp": jikan_anime.get("title_japanese"),
            "imagem": (jikan_anime.get("images") or {}).get("webp", {}).get("large_image_url"),
            "score": jikan_anime.get("score"),
            "sinopse": jikan_anime.get("synopsis"),
            "trailer_url": trailer.get("url"),
            "status": "ongoing",
        }

    def _extract_genres(self, jikan_anime: dict) -> list[str]:
        return [g["name"] for g in (jikan_anime.get("genres") or [])]

    async def sync_jikan_catalog(self):
        logger.info("Iniciando sincronizacao Jikan...")
        await self.start()

        try:
            animes = await self.fetch_all_airing()
            upserted = 0
            genres_added = 0

            for jikan_anime in animes:
                anime_data = self._extract_anime_data(jikan_anime)
                if not anime_data.get("mal_id"):
                    continue

                # Check if anime already exists by slug or mal_id
                mal_id = anime_data["mal_id"]
                async with self.db._db.execute(
                    "SELECT id, slug FROM animes WHERE mal_id = ?", (mal_id,)
                ) as cur:
                    existing = await cur.fetchone()

                if existing:
                    # Update metadata only, never touch episodes
                    await self.db._db.execute("""
                        UPDATE animes SET
                            titulo = COALESCE(?, titulo),
                            titulo_en = COALESCE(?, titulo_en),
                            titulo_jp = COALESCE(?, titulo_jp),
                            imagem = COALESCE(?, imagem),
                            score = ?,
                            sinopse = COALESCE(?, sinopse),
                            trailer_url = COALESCE(?, trailer_url),
                            status = ?,
                            next_check_at = datetime('now'),
                            updated_at = datetime('now')
                        WHERE id = ?
                    """, (
                        anime_data["titulo"],
                        anime_data["titulo_en"],
                        anime_data["titulo_jp"],
                        anime_data["imagem"],
                        anime_data["score"],
                        anime_data["sinopse"],
                        anime_data["trailer_url"],
                        anime_data["status"],
                        existing[0],
                    ))
                else:
                    # New anime from Jikan - needs a slug
                    # Use title slugified as temporary slug
                    title = anime_data["titulo"] or "unknown"
                    slug = title.lower().replace(" ", "-")
                    slug = "".join(c for c in slug if c.isalnum() or c == "-")
                    slug = slug.strip("-")

                    anime_data["slug"] = slug
                    anime_data["tipo"] = "legendado"
                    await self.db.upsert_anime(anime_data)

                    # Set next_check_at for ongoing
                    async with self.db._db.execute(
                        "SELECT id FROM animes WHERE slug = ?", (slug,)
                    ) as cur:
                        row = await cur.fetchone()
                        if row:
                            await self.db._db.execute("""
                                UPDATE animes SET next_check_at = datetime('now') WHERE id = ?
                            """, (row[0],))

                upserted += 1

                # Add genres
                genres = self._extract_genres(jikan_anime)
                for g_name in genres:
                    genero_id = await self.db.upsert_genero(g_name)
                    async with self.db._db.execute(
                        "SELECT id FROM animes WHERE mal_id = ?", (mal_id,)
                    ) as cur:
                        row = await cur.fetchone()
                        if row:
                            await self.db.link_anime_genero(row[0], genero_id)
                            genres_added += 1

            await self.db._db.commit()
            logger.info(
                f"Sincronizacao Jikan concluida: {upserted} animes processados, "
                f"{genres_added} links de genero"
            )

        finally:
            await self.close()
