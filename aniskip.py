import logging
import aiohttp

logger = logging.getLogger("Aniskip")

ANISKIP_BASE = "https://api.aniskip.com/v2/skip-times"
ANISKIP_TIMEOUT = 10


async def fetch_skip_times(mal_id: int, ep_numero: int, episode_length: int = 1440,
                           session: aiohttp.ClientSession = None) -> dict:
    url = f"{ANISKIP_BASE}/{mal_id}/{ep_numero}"
    params = {
        "types[]": ["op", "ed"],
        "episodeLength": episode_length,
    }

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=ANISKIP_TIMEOUT),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get("results", [])

                skip_times = {}
                for item in results:
                    skip_type = item.get("skipType")
                    if skip_type in ("op", "ed"):
                        interval = item.get("interval", {})
                        start = interval.get("startTime", item.get("startTime", 0))
                        end = interval.get("endTime", item.get("endTime", 0))
                        skip_times[skip_type] = {
                            "start": start,
                            "end": end,
                        }
                return skip_times

            elif resp.status == 404:
                return {}

            else:
                logger.warning(f"Aniskip {resp.status} para mal_id={mal_id} ep={ep_numero}")
                return {}

    except Exception as e:
        logger.debug(f"Aniskip erro para mal_id={mal_id} ep={ep_numero}: {e}")
        return {}
    finally:
        if close_session:
            await session.close()


async def fetch_and_save_skip_times(db, mal_id: int, ep_numero: int):
    if not mal_id:
        return

    async with db._db.execute(
        "SELECT id FROM animes WHERE mal_id = ?", (mal_id,)
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return
        anime_id = row[0]

    async with aiohttp.ClientSession() as session:
        skip_times = await fetch_skip_times(mal_id, ep_numero, session=session)

    for skip_type, times in skip_times.items():
        await db.upsert_skip_time(
            anime_id=anime_id,
            ep_numero=ep_numero,
            tipo=skip_type,
            start_time=times["start"],
            end_time=times["end"],
        )

    if skip_times:
        logger.debug(
            f"Skip times salvos: mal_id={mal_id} ep={ep_numero} "
            f"tipos={list(skip_times.keys())}"
        )
