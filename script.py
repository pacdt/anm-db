import asyncio
import aiohttp
import aiofiles
import json
import os
import random
from datetime import datetime
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm

# --- CONFIGURAÇÕES ---
BASE_URL_SITE = "https://animefire.plus"
BASE_URL_VIDEO = "https://animefire.plus/video"

# Pastas de Origem (Sincronizado com api.py)
FOLDER_DUBLADOS = os.path.join('Episodios', 'Dublados')
FOLDER_LEGENDADOS = os.path.join('Episodios', 'Legendados')

# Performance e Segurança
MAX_CONCURRENT_REQUESTS = 20  # Total de workers simultâneos
MAX_RETRIES_404 = 5           # Episódios vazios antes de pular o anime
TIMEOUT_SECONDS = 15

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": BASE_URL_SITE,
        "X-Requested-With": "XMLHttpRequest"
    }

# --- AUXILIARES ---

async def save_json(path, data):
    async with aiofiles.open(path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))

async def load_json(path):
    if not os.path.exists(path): return None
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            return json.loads(await f.read())
    except: return None

def extrair_slug(url):
    return url.rstrip('/').split('/')[-1].replace('-todos-os-episodios', '')

# --- CORE ---

async def fetch(session, url):
    try:
        async with session.get(url, headers=get_headers(), timeout=TIMEOUT_SECONDS) as response:
            if response.status == 200:
                if "application/json" in response.headers.get('Content-Type', ''):
                    return await response.json(), 200
                return await response.text(), 200
            if response.status == 429:
                await asyncio.sleep(20) # Pausa por excesso de requisições
            return None, response.status
    except:
        return None, 0

async def mapear_catalogo(session, tipo, paginas):
    animes = {}
    base = f"{BASE_URL_SITE}/lista-de-animes-{tipo}s"
    
    tasks = [fetch(session, base if p == 1 else f"{base}/{p}") for p in range(1, paginas + 1)]
    
    for html, status in await tqdm.gather(*tasks, desc=f"Lendo lista {tipo}", unit="pg"):
        if status == 200 and html:
            soup = BeautifulSoup(html, 'html.parser')
            for link in soup.find_all('a', href=True):
                h3 = link.find('h3', class_='animeTitle')
                if h3 and '/animes/' in link['href']:
                    slug = extrair_slug(link['href'])
                    animes[slug] = {'nome': h3.get_text(strip=True), 'slug': slug, 'link': link['href']}
    return list(animes.values())

async def processar_anime(session, sem, anime, pasta):
    async with sem:
        path = os.path.join(pasta, f"{anime['slug']}.json")
        dados = await load_json(path) or {"nome": anime['nome'], "slug": anime['slug'], "episodios": []}
        
        ultimo = dados['episodios'][-1]['numero'] if dados['episodios'] else 0
        prox, erros, novos = ultimo + 1, 0, False
        
        while erros < MAX_RETRIES_404:
            await asyncio.sleep(random.uniform(0.1, 0.4)) # Delay humano
            resp, status = await fetch(session, f"{BASE_URL_VIDEO}/{anime['slug']}/{prox}")
            
            if status == 200 and resp:
                link = resp.get('token') or (resp['data'][-1]['src'] if resp.get('data') else None)
                if link:
                    dados['episodios'].append({"numero": prox, "url": link})
                    novos, erros = True, 0
                    prox += 1
                    continue
            
            erros += 1
            prox += 1
            
        if novos:
            dados['episodios'].sort(key=lambda x: x['numero'])
            await save_json(path, dados)
            return True
    return False

async def main():
    print(f"=== INICIANDO ATUALIZAÇÃO: {datetime.now().strftime('%H:%M:%S')} ===")
    os.makedirs(FOLDER_DUBLADOS, exist_ok=True)
    os.makedirs(FOLDER_LEGENDADOS, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        # 1. Mapeia o que existe no site
        animes_dub = await mapear_catalogo(session, 'dublado', 30)
        animes_leg = await mapear_catalogo(session, 'legendado', 190)
        
        all_tasks = []
        sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        # 2. Prepara verificação de episódios
        for a in animes_dub: all_tasks.append(processar_anime(session, sem, a, FOLDER_DUBLADOS))
        for a in animes_leg: all_tasks.append(processar_anime(session, sem, a, FOLDER_LEGENDADOS))
        
        # 3. Executa com progresso
        results = [await f for f in tqdm(asyncio.as_completed(all_tasks), total=len(all_tasks), desc="Verificando episódios", unit="anime")]
        
    print(f"=== CICLO CONCLUÍDO: {sum(1 for r in results if r)} animes com novos episódios. ===")

if __name__ == "__main__":
    if os.name == 'nt': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())