import os
import asyncio
import aiohttp
import random
import logging
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from db import DatabaseManager
from cdn_checker import check_cdn_episode
from aniskip import fetch_and_save_skip_times

# --- CONFIGURACOES GERAIS ---
BASE_URL_SITE = "https://animefire.plus"
BASE_URL_VIDEO = "https://animefire.plus/video"

# --- CONFIGURACOES OTIMIZADAS ---
REQ_CATALOGO = 3
CONCURRENCY_CATALOGO = 3

REQ_EPISODIOS = 5
CONCURRENCY_EPISODIOS = 8

MAX_EPISODIOS_FRENTE = 10
ERROS_CONSECUTIVOS_LIMITE = 2

DELAY_ENTRE_BATCHES = 2
DELAY_APOS_429 = 15

TIMEOUT_GLOBAL = 30

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("Scraper")

# --- UTILITARIOS ---

def formatar_tempo(segundos):
    return str(timedelta(seconds=int(segundos)))

# --- RATE LIMITER MELHORADO ---
class RateLimiter:
    def __init__(self, rate_limit):
        self.rate_limit = rate_limit
        self.tokens = rate_limit
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()
        self.consecutive_429 = 0

    async def wait(self):
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.tokens = min(self.rate_limit, self.tokens + elapsed * self.rate_limit)
            self.updated_at = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate_limit
                await asyncio.sleep(wait_time)
                self.tokens = 0
                self.updated_at = time.monotonic()
            else:
                self.tokens -= 1

        base_jitter = 0.1 + (self.consecutive_429 * 0.05)
        await asyncio.sleep(random.uniform(base_jitter, base_jitter + 0.1))

    async def report_429(self):
        async with self.lock:
            self.consecutive_429 += 1
            self.tokens = 0
            self.updated_at = time.monotonic()

    async def report_success(self):
        async with self.lock:
            if self.consecutive_429 > 0:
                self.consecutive_429 = max(0, self.consecutive_429 - 1)

def get_header():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": BASE_URL_SITE,
        "Connection": "keep-alive",
    }

def extrair_slug(url_anime):
    if not url_anime: return ""
    url_clean = url_anime.split('?')[0]
    if '/animes/' in url_clean:
        slug = url_clean.split('/animes/')[-1]
    else:
        slug = url_clean.rstrip('/').split('/')[-1]
    return slug.replace('-todos-os-episodios', '')

# --- CORE ---

class AnimeScraper:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.limiter_catalogo = RateLimiter(REQ_CATALOGO)
        self.limiter_episodios = RateLimiter(REQ_EPISODIOS)

        self.sem_catalogo = asyncio.Semaphore(CONCURRENCY_CATALOGO)
        self.sem_episodios = asyncio.Semaphore(CONCURRENCY_EPISODIOS)

        self.session = None
        self.total_429 = 0

    async def start_session(self):
        limit_total = CONCURRENCY_CATALOGO + CONCURRENCY_EPISODIOS + 5
        connector = aiohttp.TCPConnector(limit=limit_total, ttl_dns_cache=300, ssl=False)
        self.session = aiohttp.ClientSession(
            headers=get_header(),
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_GLOBAL)
        )

    async def close_session(self):
        if self.session:
            await self.session.close()

    async def fetch(self, url, json_response=False, use_episodios=False):
        retries = 3
        backoff_base = 3

        limiter = self.limiter_episodios if use_episodios else self.limiter_catalogo
        sem = self.sem_episodios if use_episodios else self.sem_catalogo

        for i in range(retries):
            await limiter.wait()

            async with sem:
                try:
                    async with self.session.get(url) as response:
                        status = response.status

                        if status == 200:
                            await limiter.report_success()
                            if json_response:
                                try:
                                    return await response.json()
                                except:
                                    return None
                            return await response.read()

                        elif status in [429, 503]:
                            self.total_429 += 1
                            await limiter.report_429()

                            wait_time = DELAY_APOS_429 + (backoff_base ** i) + random.uniform(2, 5)

                            if self.total_429 % 20 == 1:
                                logger.warning(f"Rate limit {status} (Total: {self.total_429}). Pausando {wait_time:.1f}s...")

                            await asyncio.sleep(wait_time)
                            continue

                        elif status == 404:
                            return None

                except Exception as e:
                    if i == retries - 1:
                        pass

            await asyncio.sleep(0.5)
        return None

    # --- CATALOGO ---
    async def processar_pagina_catalogo(self, url):
        content = await self.fetch(url, use_episodios=False)
        if not content: return []

        try:
            soup = BeautifulSoup(content, 'html.parser')
            animes = []
            links = soup.select('article.min_video_card a, div.animeCard a, h3.animeTitle a, a[href*="/animes/"]')

            seen = set()
            for link in links:
                href = link.get('href')
                if not href or '/animes/' not in href or href in seen:
                    continue
                seen.add(href)

                title_tag = link.find('h3') or link.find('span', class_='title')
                nome = title_tag.get_text(strip=True) if title_tag else "Desconhecido"

                img = link.find('img')
                src = img.get('data-src') or img.get('src') if img else None

                animes.append({
                    'nome': nome,
                    'link': href,
                    'imagem': src,
                    'slug': extrair_slug(href)
                })
            return animes
        except:
            return []

    async def mapear_catalogo(self, tipo, paginas_max):
        logger.info(f"Mapeando catalogo {tipo.upper()} ({paginas_max} paginas)...")
        base = f"{BASE_URL_SITE}/lista-de-animes-{tipo}s"

        tasks = [
            self.processar_pagina_catalogo(base if p==1 else f"{base}/{p}")
            for p in range(1, paginas_max + 1)
        ]
        results = await asyncio.gather(*tasks)

        animes_unicos = {}
        for lista in results:
            for anime in lista:
                animes_unicos[anime['slug']] = anime

        lista_final = list(animes_unicos.values())
        logger.info(f"Catalogo {tipo}: {len(lista_final)} animes encontrados")
        return lista_final

    # --- EPISODIOS ---
    async def obter_link_video(self, slug, numero):
        url = f"{BASE_URL_VIDEO}/{slug}/{numero}"
        data = await self.fetch(url, json_response=True, use_episodios=True)

        if not data:
            return None

        try:
            if data.get('token'):
                return data['token']

            if data.get('video'):
                return data['video']

            lista_dados = data.get('data')
            if lista_dados and isinstance(lista_dados, list) and len(lista_dados) > 0:
                ultimo = lista_dados[-1]
                if isinstance(ultimo, dict):
                    return ultimo.get('src') or ultimo.get('url') or ultimo.get('video')
                return ultimo

        except Exception as e:
            logger.debug(f"Erro ao processar video {slug}/{numero}: {e}")

        return None

    async def atualizar_anime(self, anime, tipo):
        slug = anime['slug']

        existing = await self.db.get_anime_by_slug(slug)
        if existing:
            anime_id = existing["id"]
            mal_id = existing.get("mal_id")
        else:
            mal_id = None
            anime_id = await self.db.upsert_anime({
                "slug": slug,
                "tipo": tipo,
                "titulo": anime['nome'],
                "imagem": anime.get('imagem'),
            })

        # CDN uses base slug (without -dublado)
        cdn_slug = slug.replace("-dublado", "") if slug.endswith("-dublado") else slug

        ultimo_ep = await self.db.get_ultimo_episodio(slug)
        proximo_ep = ultimo_ep + 1

        novos_eps = []
        cdn_hits = 0
        af_fallbacks = 0
        current_check = proximo_ep
        erros_consecutivos = 0
        max_tentativas = ultimo_ep + MAX_EPISODIOS_FRENTE if ultimo_ep > 0 else MAX_EPISODIOS_FRENTE

        while current_check <= max_tentativas and erros_consecutivos < ERROS_CONSECUTIVOS_LIMITE:
            cdn_url = await check_cdn_episode(cdn_slug, current_check, self.session)

            if cdn_url:
                await self.db.upsert_episodio(
                    anime_id=anime_id,
                    numero=current_check,
                    titulo=f"Episodio {current_check}",
                    url_cdn=cdn_url,
                    fonte_ativa="cdn",
                )
                novos_eps.append(current_check)
                cdn_hits += 1
                erros_consecutivos = 0
                current_check += 1
                if mal_id:
                    asyncio.create_task(fetch_and_save_skip_times(self.db, mal_id, current_check - 1))
            else:
                link = await self.obter_link_video(slug, current_check)
                if link:
                    await self.db.upsert_episodio(
                        anime_id=anime_id,
                        numero=current_check,
                        titulo=f"Episodio {current_check}",
                        url_af=link,
                        fonte_ativa="animefire",
                    )
                    novos_eps.append(current_check)
                    af_fallbacks += 1
                    erros_consecutivos = 0
                    current_check += 1
                    if mal_id:
                        asyncio.create_task(fetch_and_save_skip_times(self.db, mal_id, current_check - 1))
                else:
                    erros_consecutivos += 1
                    current_check += 1

        if ultimo_ep == 0 and not novos_eps:
            for ep_num in range(1, MAX_EPISODIOS_FRENTE + 1):
                cdn_url = await check_cdn_episode(cdn_slug, ep_num, self.session)
                if cdn_url:
                    await self.db.upsert_episodio(
                        anime_id=anime_id,
                        numero=ep_num,
                        titulo=f"Episodio {ep_num}",
                        url_cdn=cdn_url,
                        fonte_ativa="cdn",
                    )
                    novos_eps.append(ep_num)
                    cdn_hits += 1
                    if mal_id:
                        asyncio.create_task(fetch_and_save_skip_times(self.db, mal_id, ep_num))
                else:
                    link = await self.obter_link_video(slug, ep_num)
                    if link:
                        await self.db.upsert_episodio(
                            anime_id=anime_id,
                            numero=ep_num,
                            titulo=f"Episodio {ep_num}",
                            url_af=link,
                            fonte_ativa="animefire",
                        )
                        novos_eps.append(ep_num)
                        af_fallbacks += 1
                        if mal_id:
                            asyncio.create_task(fetch_and_save_skip_times(self.db, mal_id, ep_num))
                    else:
                        if ep_num == 1:
                            break

        return len(novos_eps), bool(novos_eps), cdn_hits, af_fallbacks

    async def processar_lista(self, lista, tipo):
        if not lista:
            return

        logger.info(f"Processando {len(lista)} animes ({tipo})...")

        async def worker(anime):
            novos_eps, e_novo, cdn_hits, af_fallbacks = await self.atualizar_anime(anime, tipo)
            return anime['slug'], novos_eps, e_novo, cdn_hits, af_fallbacks

        tasks = [worker(anime) for anime in lista]

        total = len(tasks)
        done = 0
        novos_animes = 0
        total_eps_novos = 0
        total_cdn_hits = 0
        total_af_fallbacks = 0
        start_t = time.monotonic()
        last_slug = ""
        batch_count = 0

        for f in asyncio.as_completed(tasks):
            slug, novos_eps, e_novo, cdn_hits, af_fallbacks = await f
            last_slug = slug
            done += 1

            if e_novo:
                novos_animes += 1
            if novos_eps > 0:
                total_eps_novos += novos_eps
            total_cdn_hits += cdn_hits
            total_af_fallbacks += af_fallbacks

            batch_count += 1
            if batch_count % 50 == 0:
                await asyncio.sleep(DELAY_ENTRE_BATCHES)

            elapsed = time.monotonic() - start_t
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            pct = (done / total) * 100 if total else 0

            if done % 10 == 0 or done == total:
                msg = f"   [{pct:5.1f}%] {done}/{total} | Novos: {novos_animes} | Eps+: {total_eps_novos} | {rate:4.1f}/s | 429s: {self.total_429} | {last_slug[:25]}"
                print(msg, end='\r')

        print()
        tempo_formatado = formatar_tempo(time.monotonic() - start_t)
        total_all = total_cdn_hits + total_af_fallbacks
        cdn_pct = (total_cdn_hits / total_all * 100) if total_all > 0 else 0
        af_pct = (total_af_fallbacks / total_all * 100) if total_all > 0 else 0
        logger.info(f"Concluido: {novos_animes} animes novos | {total_eps_novos} eps novos | CDN: {total_cdn_hits} ({cdn_pct:.0f}%) | AF: {total_af_fallbacks} ({af_pct:.0f}%) | 429s: {self.total_429} | Tempo: {tempo_formatado}")

async def main():
    print("=" * 60)
    print("ANIME SCRAPER - MODO ESTVEL (ANTI RATE-LIMIT)")
    print("=" * 60)
    print(f"Config: Catalogo {REQ_CATALOGO}/s | Episodios {REQ_EPISODIOS}/s")
    print(f"Protecoes: Delay {DELAY_ENTRE_BATCHES}s/lote | Pausa 429: {DELAY_APOS_429}s")
    print(f"Busca: Ate {MAX_EPISODIOS_FRENTE} eps a frente | Limite erros: {ERROS_CONSECUTIVOS_LIMITE}")
    print("=" * 60)

    db = DatabaseManager()
    await db.init_db()
    scraper = AnimeScraper(db)

    start_time = datetime.now()
    print(f"\n[{start_time.strftime('%H:%M:%S')}] Iniciando varredura...")

    try:
        await scraper.start_session()
        scraper.total_429 = 0

        # Get existing slugs from DB
        existing_slugs = set(await db.list_all_slugs())

        logger.info("\nFASE 1: Mapeamento de Catalogos")
        dub = await scraper.mapear_catalogo('dublado', 32)
        leg = await scraper.mapear_catalogo('legendado', 200)

        logger.info("\nFASE 2: Atualizacao de Episodios")
        await scraper.processar_lista(dub, "dublado")
        await scraper.processar_lista(leg, "legendado")

    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
    finally:
        await scraper.close_session()
        await db.close()
        elapsed = datetime.now() - start_time
        print("\n" + "=" * 60)
        print(f"Varredura finalizada em {elapsed}")
        print(f"Total de rate limits: {scraper.total_429}")
        print("=" * 60)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nParado pelo usuario.")
