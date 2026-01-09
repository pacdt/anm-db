import os
import json
import asyncio
import aiohttp
import aiofiles
import random
import logging
import time
from datetime import datetime
from bs4 import BeautifulSoup

# --- CONFIGURAÇÕES GERAIS ---
BASE_URL_SITE = "https://animefire.plus"
BASE_URL_VIDEO = "https://animefire.plus/video"

PAGINAS_DUBLADOS = 32
PAGINAS_LEGENDADOS = 200

ARQUIVO_LISTA_DUBLADOS = 'animes_dublados.json'
ARQUIVO_LISTA_LEGENDADOS = 'animes_legendados.json'
FOLDER_DUBLADOS = os.path.join('Episodios', 'Dublados')
FOLDER_LEGENDADOS = os.path.join('Episodios', 'Legendados')

# --- CALIBRAGEM DE VELOCIDADE (HÍBRIDA) ---
# CATÁLOGO: Mantemos seguro para não falhar na listagem principal.
REQ_CATALOGO = 4
CONCURRENCY_CATALOGO = 4

# EPISÓDIOS: "Velocidade Máxima" solicitada.
# APIs JSON costumam ser mais leves. Vamos acelerar aqui.
REQ_EPISODIOS = 10
CONCURRENCY_EPISODIOS = 10

TIMEOUT_GLOBAL = 30

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("Scraper")

# --- RATE LIMITER PRECISO ---
class RateLimiter:
    def __init__(self, rate_limit):
        self.rate_limit = rate_limit
        self.tokens = rate_limit
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()

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
        
        # Adiciona "jitter" (atraso aleatório) para evitar padrão robótico perfeito
        # Variação de 10% a 30% do tempo médio entre requisições
        await asyncio.sleep(random.uniform(0.05, 0.15))

# --- UTILITÁRIOS ---

def get_header():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Referer": BASE_URL_SITE,
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1"
    }

def criar_pastas():
    for p in [FOLDER_DUBLADOS, FOLDER_LEGENDADOS]:
        os.makedirs(p, exist_ok=True)

def extrair_slug(url_anime):
    if not url_anime: return ""
    url_clean = url_anime.split('?')[0]
    if '/animes/' in url_clean:
        slug = url_clean.split('/animes/')[-1]
    else:
        slug = url_clean.rstrip('/').split('/')[-1]
    return slug.replace('-todos-os-episodios', '')

async def save_json_async(path, data):
    try:
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Erro save JSON {path}: {e}")

# --- CORE ---

class AnimeScraper:
    def __init__(self):
        # Limitadores separados
        self.limiter_catalogo = RateLimiter(REQ_CATALOGO)
        self.limiter_episodios = RateLimiter(REQ_EPISODIOS)
        
        # Semáforos separados
        self.sem_catalogo = asyncio.Semaphore(CONCURRENCY_CATALOGO)
        self.sem_episodios = asyncio.Semaphore(CONCURRENCY_EPISODIOS)
        
        self.session = None

    async def start_session(self):
        # Pool maior para comportar a concorrência somada (com margem)
        limit_total = CONCURRENCY_CATALOGO + CONCURRENCY_EPISODIOS + 10
        connector = aiohttp.TCPConnector(limit=limit_total, ttl_dns_cache=300, ssl=False)
        self.session = aiohttp.ClientSession(
            headers=get_header(), 
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_GLOBAL)
        )

    async def close_session(self):
        if self.session: await self.session.close()

    async def fetch(self, url, json_response=False, use_episodios=False):
        retries = 3
        backoff_base = 2
        
        # Seleciona o limitador e semáforo corretos
        limiter = self.limiter_episodios if use_episodios else self.limiter_catalogo
        sem = self.sem_episodios if use_episodios else self.sem_catalogo

        for i in range(retries):
            await limiter.wait() # Respeita o limite específico

            async with sem:
                try:
                    async with self.session.get(url) as response:
                        status = response.status
                        
                        if status == 200:
                            if json_response:
                                try: return await response.json()
                                except: return None
                            return await response.read()
                        
                        elif status in [429, 503]:
                            wait_time = backoff_base ** (i + 2) + random.uniform(1, 3)
                            logger.warning(f"⚠️ Cloudflare {status}. Pausando {wait_time:.1f}s...")
                            await asyncio.sleep(wait_time)
                            continue # Tenta de novo
                        
                        elif status == 404:
                            return None
                
                except Exception as e:
                    if i == retries - 1: pass 
            
            await asyncio.sleep(0.5) # Pequeno delay entre retries
        return None

    # --- Lógica de Catálogo ---
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
                if not href or '/animes/' not in href or href in seen: continue
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
        except: return []

    async def mapear_catalogo(self, tipo, paginas_max, arquivo_saida):
        logger.info(f"🚀 Mapeando {tipo.upper()} ({paginas_max} pgs)...")
        base = f"{BASE_URL_SITE}/lista-de-animes-{tipo}s"
        
        tasks = [self.processar_pagina_catalogo(base if p==1 else f"{base}/{p}") for p in range(1, paginas_max + 1)]
        results = await asyncio.gather(*tasks)
        
        animes_unicos = {}
        for lista in results:
            for anime in lista:
                animes_unicos[anime['slug']] = anime
        
        lista_final = list(animes_unicos.values())
        logger.info(f"✅ Catálogo {tipo}: {len(lista_final)} animes encontrados.")
        await save_json_async(arquivo_saida, lista_final)
        return lista_final

    # --- Lógica de Episódios (CORRIGIDA) ---
    async def obter_link_video(self, slug, numero):
        url = f"{BASE_URL_VIDEO}/{slug}/{numero}"
        # AQUI USAMOS O LIMITADOR DE EPISÓDIOS (RÁPIDO)
        data = await self.fetch(url, json_response=True, use_episodios=True)
        
        if not data: return None

        # CORREÇÃO DO ERRO DE INDEX: Verificação robusta
        try:
            # 1. Tenta pegar token direto
            if data.get('token'): 
                return data['token']
            
            # 2. Tenta pegar da lista 'data'
            lista_dados = data.get('data')
            if lista_dados and isinstance(lista_dados, list) and len(lista_dados) > 0:
                # Pega o último item da lista (src)
                return lista_dados[-1].get('src')
                
        except Exception as e:
            return None
            
        return None

    async def atualizar_anime(self, anime, pasta):
        slug = anime['slug']
        path = os.path.join(pasta, f"{slug}.json")
        
        dados = {"nome": anime['nome'], "slug": slug, "imagem": anime['imagem'], "episodios": []}
        if os.path.exists(path):
            try:
                async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    if content: dados.update(json.loads(content))
            except: pass
        
        last_ep = dados['episodios'][-1]['numero'] if dados['episodios'] else 0
        current_check = last_ep + 1
        
        erros_seq = 0
        novos = False
        
        # Reduzido para 1 tentativa de erro para máxima velocidade
        while erros_seq < 1:
            link = await self.obter_link_video(slug, current_check)
            if link:
                dados['episodios'].append({"numero": current_check, "url": link})
                novos = True
                erros_seq = 0
                current_check += 1
            else:
                erros_seq += 1
                current_check += 1
        
        if novos:
            dados['episodios'].sort(key=lambda x: x['numero'])
            await save_json_async(path, dados)
            return True
        return False

    async def processar_lista(self, lista, pasta):
        if not lista: return
        logger.info(f"⚡ Verificando episódios para {len(lista)} animes em {pasta}...")
        
        async def worker(anime):
            res = await self.atualizar_anime(anime, pasta)
            return anime['slug'], res
        
        tasks = [worker(anime) for anime in lista]
        
        total = len(tasks)
        done = 0
        updated = 0
        start_t = time.monotonic()
        last_slug = None
        
        for f in asyncio.as_completed(tasks):
            slug, res = await f
            last_slug = slug
            done += 1
            if res: updated += 1
            elapsed = time.monotonic() - start_t
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            pct = (done / total) * 100 if total else 0
            msg = f"   [{pct:5.1f}%] {done}/{total} | Atualizados: {updated} | Vel: {rate:4.2f}/s | T: {elapsed:6.1f}s | ETA: {eta:6.1f}s | Último: {last_slug}"
            print(msg, end='\r')
                
        print()
        print(f"   Concluído. Total Atualizados: {updated} | Tempo: {time.monotonic() - start_t:6.1f}s")

async def main():
    print(f"=== ANIME SCRAPER HÍBRIDO ===")
    print(f"   -> Catálogo: {REQ_CATALOGO} req/s (Seguro)")
    print(f"   -> Episódios: {REQ_EPISODIOS} req/s (Turbo)")
    criar_pastas()
    scraper = AnimeScraper()
    
    while True:
        start_time = datetime.now()
        print(f"\n[{start_time.strftime('%H:%M:%S')}] Iniciando varredura...")
        
        try:
            await scraper.start_session()
            
            # DUBLADOS
            dub = await scraper.mapear_catalogo('dublado', PAGINAS_DUBLADOS, ARQUIVO_LISTA_DUBLADOS)
            await scraper.processar_lista(dub, FOLDER_DUBLADOS)
            
            # LEGENDADOS
            leg = await scraper.mapear_catalogo('legendado', PAGINAS_LEGENDADOS, ARQUIVO_LISTA_LEGENDADOS)
            await scraper.processar_lista(leg, FOLDER_LEGENDADOS)
            
        except Exception as e:
            logger.error(f"Erro fatal no Main: {e}")
        finally:
            await scraper.close_session()
            elapsed = datetime.now() - start_time
            print(f"--- Ciclo finalizado em {elapsed} ---")
            print("Dormindo 30min...")
            await asyncio.sleep(1800)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nParado pelo usuário.")
