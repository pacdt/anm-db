import os
import json
import asyncio
import logging
from db import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("Migrate")

FOLDER_DUBLADOS = os.path.join('Episodios', 'Dublados')
FOLDER_LEGENDADOS = os.path.join('Episodios', 'Legendados')


def extract_jikan_fields(metadata: dict) -> dict:
    if not metadata:
        return {}
    return {
        "mal_id": metadata.get("mal_id"),
        "score": metadata.get("score"),
        "sinopse": metadata.get("synopsis"),
        "trailer_url": (metadata.get("trailer") or {}).get("url"),
        "titulo_en": metadata.get("title_english"),
        "titulo_jp": metadata.get("title_japanese"),
        "status": "ongoing" if metadata.get("airing") else "finished",
        "generos": [g["name"] for g in (metadata.get("genres") or [])],
    }


async def migrate_file(db: DatabaseManager, filepath: str, tipo: str) -> tuple[int, int]:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Erro ao ler {filepath}: {e}")
        return 0, 0

    slug = data.get("slug", "")
    if not slug:
        return 0, 0

    jikan = extract_jikan_fields(data.get("metadata_completo"))

    anime_data = {
        "slug": slug,
        "tipo": tipo,
        "titulo": data.get("nome"),
        "titulo_en": jikan.get("titulo_en"),
        "titulo_jp": jikan.get("titulo_jp"),
        "imagem": data.get("imagem"),
        "mal_id": jikan.get("mal_id"),
        "score": jikan.get("score"),
        "sinopse": jikan.get("sinopse"),
        "trailer_url": jikan.get("trailer_url"),
        "status": jikan.get("status"),
    }

    anime_id = await db.upsert_anime(anime_data)

    for g_name in jikan.get("generos", []):
        genero_id = await db.upsert_genero(g_name)
        await db.link_anime_genero(anime_id, genero_id)

    episodes = data.get("episodios", [])
    ep_count = 0
    for ep in episodes:
        numero = ep.get("numero")
        if not numero:
            continue
        await db.upsert_episodio(
            anime_id=anime_id,
            numero=numero,
            titulo=ep.get("nome"),
            url_af=ep.get("url"),
            fonte_ativa="animefire",
        )
        ep_count += 1

    return 1, ep_count


async def main():
    db_path = os.getenv("DB_PATH", "anm.db")

    if os.path.exists(db_path):
        logger.error(f"Banco '{db_path}' ja existe. Remova-o primeiro para migrar novamente.")
        return

    db = DatabaseManager(db_path)
    await db.init_db()

    total_animes = 0
    total_episodes = 0
    errors = []

    for folder, tipo in [(FOLDER_DUBLADOS, "dublado"), (FOLDER_LEGENDADOS, "legendado")]:
        if not os.path.exists(folder):
            logger.warning(f"Pasta '{folder}' nao encontrada. Pulando.")
            continue

        files = [f for f in os.listdir(folder) if f.endswith('.json')]
        logger.info(f"Migrando {len(files)} animes de {folder}...")

        for i, filename in enumerate(files, 1):
            filepath = os.path.join(folder, filename)
            try:
                a, e = await migrate_file(db, filepath, tipo)
                total_animes += a
                total_episodes += e
            except Exception as exc:
                errors.append((filepath, str(exc)))
                logger.error(f"Erro em {filename}: {exc}")

            if i % 100 == 0:
                logger.info(f"  Progresso: {i}/{len(files)} | Animes: {total_animes} | Eps: {total_episodes}")

    await db.close()

    logger.info("=" * 60)
    logger.info(f"MIGRACAO CONCLUIDA")
    logger.info(f"  Animes migrados:  {total_animes}")
    logger.info(f"  Episodios:        {total_episodes}")
    logger.info(f"  Erros:            {len(errors)}")
    if errors:
        for path, msg in errors[:10]:
            logger.error(f"    {path}: {msg}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
