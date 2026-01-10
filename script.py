import os
import json
import asyncio
import aiohttp
import aiofiles
import random
import logging
import time
from datetime import datetime, timedelta
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

# --- CONFIGURAÇÕES OTIMIZADAS ---
REQ_CATALOGO = 3
CONCURRENCY_CATALOGO = 3

REQ_EPISODIOS = 5
CONCURRENCY_EPISODIOS = 8

# Configuração para busca de episódios
MAX_EPISODIOS_FRENTE = 10  # Busca até 10 episódios à frente
ERROS_CONSECUTIVOS_LIMITE = 2  # Reduzido para verificar melhor

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

# --- UTILITÁRIOS ---

def formatar_tempo(segundos):
    """Converte segundos para formato HH:MM:SS"""
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

async def load_json_async(path):
    try:
        if os.path.exists(path):
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content else {}
    except:
        pass
    return {}

# --- CORE ---

class AnimeScraper:
    def __init__(self):
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
                                logger.warning(f"⚠️ Rate limit {status} (Total: {self.total_429}). Pausando {wait_time:.1f}s...")
                            
                            await asyncio.sleep(wait_time)
                            continue
                        
                        elif status == 404:
                            return None
                
                except Exception as e:
                    if i == retries - 1: 
                        pass
            
            await asyncio.sleep(0.5)
        return None

    # --- CATÁLOGO ---
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
        logger.info(f"🔍 Mapeando catálogo {tipo.upper()} ({paginas_max} páginas)...")
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
        logger.info(f"✅ Catálogo {tipo}: {len(lista_final)} animes encontrados")
        return lista_final

    async def carregar_animes_existentes(self, pasta):
        existentes = {}
        if not os.path.exists(pasta):
            return existentes
            
        for filename in os.listdir(pasta):
            if filename.endswith('.json'):
                path = os.path.join(pasta, filename)
                dados = await load_json_async(path)
                if dados and 'slug' in dados:
                    existentes[dados['slug']] = dados
        
        logger.info(f"📂 Carregados {len(existentes)} animes existentes de {pasta}")
        return existentes

    # --- EPISÓDIOS (BUSCA MELHORADA) ---
    async def obter_link_video(self, slug, numero):
        url = f"{BASE_URL_VIDEO}/{slug}/{numero}"
        data = await self.fetch(url, json_response=True, use_episodios=True)
        
        if not data: 
            return None

        try:
            # Tenta múltiplos formatos de resposta
            if data.get('token'): 
                return data['token']
            
            if data.get('video'):
                return data['video']
                
            lista_dados = data.get('data')
            if lista_dados and isinstance(lista_dados, list) and len(lista_dados) > 0:
                # Tenta pegar o último item
                ultimo = lista_dados[-1]
                if isinstance(ultimo, dict):
                    return ultimo.get('src') or ultimo.get('url') or ultimo.get('video')
                return ultimo
                
        except Exception as e:
            logger.debug(f"Erro ao processar vídeo {slug}/{numero}: {e}")
            
        return None

    async def atualizar_anime(self, anime, pasta, animes_existentes):
        slug = anime['slug']
        path = os.path.join(pasta, f"{slug}.json")
        
        if slug in animes_existentes:
            dados = animes_existentes[slug].copy()
            dados['nome'] = anime['nome']
            dados['imagem'] = anime.get('imagem') or dados.get('imagem')
        else:
            dados = {
                "nome": anime['nome'], 
                "slug": slug, 
                "imagem": anime['imagem'], 
                "episodios": []
            }
        
        episodios_atuais = {ep['numero']: ep for ep in dados.get('episodios', [])}
        ultimo_ep = max(episodios_atuais.keys()) if episodios_atuais else 0
        
        # BUSCA MELHORADA: Tenta tanto episódios novos quanto verificação de gaps
        novos_eps = []
        
        # 1. Busca episódios novos sequencialmente
        current_check = ultimo_ep + 1
        erros_consecutivos = 0
        max_tentativas = ultimo_ep + MAX_EPISODIOS_FRENTE
        
        while current_check <= max_tentativas and erros_consecutivos < ERROS_CONSECUTIVOS_LIMITE:
            if current_check in episodios_atuais:
                current_check += 1
                erros_consecutivos = 0  # Reset se já existe
                continue
                
            link = await self.obter_link_video(slug, current_check)
            
            if link:
                novos_eps.append({
                    "numero": current_check, 
                    "url": link,
                    "nome": f"Episódio {current_check}"
                })
                erros_consecutivos = 0
                current_check += 1
            else:
                erros_consecutivos += 1
                current_check += 1
        
        # 2. Para animes novos, tenta buscar do episódio 1
        if not episodios_atuais and not novos_eps:
            for ep_num in range(1, MAX_EPISODIOS_FRENTE + 1):
                link = await self.obter_link_video(slug, ep_num)
                if link:
                    novos_eps.append({
                        "numero": ep_num, 
                        "url": link,
                        "nome": f"Episódio {ep_num}"
                    })
                else:
                    # Se o episódio 1 não existe, provavelmente não tem nada
                    if ep_num == 1:
                        break
        
        if novos_eps:
            dados['episodios'].extend(novos_eps)
            dados['episodios'].sort(key=lambda x: x['numero'])
            await save_json_async(path, dados)
            return len(novos_eps), True
        
        if slug not in animes_existentes:
            await save_json_async(path, dados)
            return 0, True
            
        return 0, False

    async def processar_lista(self, lista, pasta, tipo):
        if not lista: 
            return
            
        animes_existentes = await self.carregar_animes_existentes(pasta)
        
        logger.info(f"⚡ Processando {len(lista)} animes ({tipo})...")
        logger.info(f"   📊 Existentes: {len(animes_existentes)} | Novos: {len(lista) - len(animes_existentes)}")
        
        async def worker(anime):
            novos_eps, e_novo = await self.atualizar_anime(anime, pasta, animes_existentes)
            return anime['slug'], novos_eps, e_novo
        
        tasks = [worker(anime) for anime in lista]
        
        total = len(tasks)
        done = 0
        novos_animes = 0
        total_eps_novos = 0
        start_t = time.monotonic()
        last_slug = ""
        batch_count = 0
        
        for f in asyncio.as_completed(tasks):
            slug, novos_eps, e_novo = await f
            last_slug = slug
            done += 1
            
            if e_novo:
                novos_animes += 1
            if novos_eps > 0:
                total_eps_novos += novos_eps
                
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
        logger.info(f"✅ Concluído: {novos_animes} animes novos | {total_eps_novos} episódios novos | {self.total_429} rate limits | Tempo: {tempo_formatado}")

async def main():
    print("=" * 60)
    print("🎬 ANIME SCRAPER - MODO ESTÁVEL (ANTI RATE-LIMIT)")
    print("=" * 60)
    print(f"📊 Config: Catálogo {REQ_CATALOGO}/s | Episódios {REQ_EPISODIOS}/s")
    print(f"🛡️  Proteções: Delay {DELAY_ENTRE_BATCHES}s/lote | Pausa 429: {DELAY_APOS_429}s")
    print(f"🔍 Busca: Até {MAX_EPISODIOS_FRENTE} eps à frente | Limite erros: {ERROS_CONSECUTIVOS_LIMITE}")
    print("=" * 60)
    
    criar_pastas()
    scraper = AnimeScraper()
    
    start_time = datetime.now()
    print(f"\n[{start_time.strftime('%H:%M:%S')}] 🚀 Iniciando varredura...")
    
    try:
        await scraper.start_session()
        
        scraper.total_429 = 0
        
        # Apaga catálogos antigos
        for arquivo in [ARQUIVO_LISTA_DUBLADOS, ARQUIVO_LISTA_LEGENDADOS]:
            if os.path.exists(arquivo):
                os.remove(arquivo)
                logger.info(f"🗑️  Removido catálogo antigo: {arquivo}")
        
        logger.info("\n📋 FASE 1: Mapeamento de Catálogos")
        dub = await scraper.mapear_catalogo('dublado', PAGINAS_DUBLADOS)
        await save_json_async(ARQUIVO_LISTA_DUBLADOS, dub)
        
        leg = await scraper.mapear_catalogo('legendado', PAGINAS_LEGENDADOS)
        await save_json_async(ARQUIVO_LISTA_LEGENDADOS, leg)
        
        logger.info("\n📺 FASE 2: Atualização de Episódios")
        await scraper.processar_lista(dub, FOLDER_DUBLADOS, "DUBLADOS")
        await scraper.processar_lista(leg, FOLDER_LEGENDADOS, "LEGENDADOS")
        
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}", exc_info=True)
    finally:
        await scraper.close_session()
        elapsed = datetime.now() - start_time
        print("\n" + "=" * 60)
        print(f"✅ Varredura finalizada em {elapsed}")
        print(f"📊 Total de rate limits: {scraper.total_429}")
        print("=" * 60)

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⛔ Parado pelo usuário.")