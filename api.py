import json
import os
import requests
import time
import re
import random
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# --- CONFIGURAÇÕES ---
# Pastas de Origem (Onde estão os dados baixados pelo Scraper)
FOLDER_DUBLADOS = os.path.join('Episodios', 'Dublados')
FOLDER_LEGENDADOS = os.path.join('Episodios', 'Legendados')

# Pastas de Destino (API Estática)
OUTPUT_API_DIR = "api_dist"
CACHE_DIR = "jikan_cache"
API_V1 = os.path.join(OUTPUT_API_DIR, "v1")
API_ANIMES_DIR = os.path.join(API_V1, "animes")
API_GENRES_DIR = os.path.join(API_V1, "genres")

# Configurações Jikan
BASE_API_JIKAN_ANIME = "https://api.jikan.moe/v4/anime"
MAX_WORKERS_API = 4  # Um pouco mais rápido pois é apenas geração
DELAY_JIKAN = 1.2
jikan_lock = Lock()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

def get_random_header():
    return {"User-Agent": random.choice(USER_AGENTS)}

# --- UTILITÁRIOS ---

def criar_pastas():
    dirs = [CACHE_DIR, API_V1, API_ANIMES_DIR, API_GENRES_DIR]
    for p in dirs:
        if not os.path.exists(p):
            os.makedirs(p)

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", str(filename)).strip()

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extrair_slug(url_anime):
    if '/animes/' in url_anime:
        slug = url_anime.split('/animes/')[-1]
    else:
        slug = url_anime.rstrip('/').split('/')[-1]
    return slug.replace('-todos-os-episodios', '')

# --- INTEGRAÇÃO JIKAN (CACHE) ---

def get_jikan_data_cached(mal_id, title):
    """Lê do cache ou busca na API Jikan com controle de taxa"""
    identifier = str(mal_id) if mal_id else title
    safe_name = sanitize_filename(identifier)
    cache_file = os.path.join(CACHE_DIR, f"{safe_name}.json")
    
    # 1. Tenta Cache
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass

    # 2. Busca API (Thread Safe)
    with jikan_lock:
        try:
            time.sleep(DELAY_JIKAN)
            if mal_id:
                url = f"{BASE_API_JIKAN_ANIME}/{mal_id}/full"
                response = requests.get(url, headers=get_random_header(), timeout=10)
            else:
                params = {"q": title, "limit": 1}
                response = requests.get(BASE_API_JIKAN_ANIME, params=params, headers=get_random_header(), timeout=10)
            
            if response.status_code == 200:
                data = response.json().get('data')
                res = data[0] if isinstance(data, list) else data
                if res:
                    save_json(cache_file, res) # Salva no cache
                return res
            elif response.status_code == 429:
                print(f" [Rate Limit] Jikan pausando 5s para: {title}")
                time.sleep(5)
        except Exception as e:
            print(f" [Erro Jikan] {title}: {e}")
    return None

# --- CORE: PROCESSAMENTO DA API ---

def process_api_item(args):
    tipo, path = args
    try:
        with open(path, 'r', encoding='utf-8') as f:
            local = json.load(f)
    except Exception as e:
        print(f"Erro ao ler arquivo {path}: {e}")
        return None

    # --- REGRA DE NEGÓCIO: IGNORAR ANIMES SEM EPISÓDIOS ---
    lista_episodios = local.get('episodios', [])
    if not lista_episodios:
        return None
    # ------------------------------------------------------

    # Dados Básicos
    mal_id = local.get('metadata_completo', {}).get('id_mal')
    jikan = get_jikan_data_cached(mal_id, local['nome'])

    # Montagem do Objeto API (Mesclagem Completa)
    
    api_obj = {}

    if jikan:
        # 1. Copia TUDO que veio do Jikan (status, aired, producers, studios, background, etc.)
        api_obj = jikan.copy()
        
        # 2. Normaliza campos para compatibilidade com Frontend antigo/simples
        
        # Flatten Image (URL direta na raiz)
        api_obj['image'] = jikan.get('images', {}).get('webp', {}).get('large_image_url')
        
        # Flatten Trailer (URL direta na raiz)
        trailer_data = jikan.get('trailer', {})
        api_obj['trailer_url'] = trailer_data.get('url') or trailer_data.get('embed_url')
        
        # Titles
        api_obj['title'] = jikan.get('title')
        api_obj['title_english'] = jikan.get('title_english') or api_obj['title']
        api_obj['title_japanese'] = jikan.get('title_japanese')
        
        # Genres (Lista simples de strings, além da lista de objetos que já vem no copy)
        api_obj['genres'] = [g['name'] for g in jikan.get('genres', [])]

    else:
        # Fallback se não achou no Jikan
        api_obj['title'] = local.get('nome')
        api_obj['title_english'] = local.get('nome')
        api_obj['title_japanese'] = None
        api_obj['image'] = local.get('imagem')
        api_obj['score'] = None
        api_obj['synopsis'] = None
        api_obj['trailer_url'] = None
        api_obj['genres'] = []

    # 3. IMPÕE DADOS DO SISTEMA LOCAL (Prioridade Máxima)
    # Estes dados sobrescrevem qualquer coisa do Jikan se houver conflito
    
    # O ID deve ser preferencialmente o do Jikan, mas garantimos que o campo 'id' exista na raiz
    api_obj['id'] = jikan.get('mal_id') if jikan else mal_id
    
    # Dados locais essenciais
    api_obj['slug'] = local['slug']
    api_obj['type'] = tipo
    
    # IMPORTANTE: A lista de episódios do Jikan é apenas um número (count).
    # Nós sobrescrevemos com a nossa lista de objetos contendo os LINKS.
    api_obj['episodes'] = lista_episodios

    # Salvar arquivo individual do anime
    destino = os.path.join(API_ANIMES_DIR, f"{local['slug']}.json")
    save_json(destino, api_obj)
    
    # Retornar metadados para construção dos índices
    return {
        "summary": api_obj,
        # Mantemos a referência aos gêneros originais (dicts) para a lógica do main
        "genres": jikan.get('genres', []) if jikan else [], 
        "last_updated": os.path.getmtime(path), 
        "latest_episode": lista_episodios[-1] if lista_episodios else None
    }

def main():
    print("=== GERADOR DE API (MODO OFFLINE/CACHE) ===")
    criar_pastas()

    # 1. Coletar arquivos locais
    tasks = []
    if os.path.exists(FOLDER_DUBLADOS):
        for f in os.listdir(FOLDER_DUBLADOS):
            if f.endswith('.json'): tasks.append(('dublado', os.path.join(FOLDER_DUBLADOS, f)))
            
    if os.path.exists(FOLDER_LEGENDADOS):
        for f in os.listdir(FOLDER_LEGENDADOS):
            if f.endswith('.json'): tasks.append(('legendado', os.path.join(FOLDER_LEGENDADOS, f)))

    total = len(tasks)
    print(f">>> Encontrados {total} arquivos locais. Iniciando processamento...")

    # 2. Processar em paralelo
    results = []
    processed_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_API) as executor:
        futures = executor.map(process_api_item, tasks)
        
        for res in futures:
            processed_count += 1
            if processed_count % 50 == 0:
                print(f"    Progresso: {processed_count}/{total}...")
            if res:
                results.append(res)

    print(f">>> Processamento concluído. Gerando índices para {len(results)} animes válidos.")

    # 3. Gerar Índices Globais (All e Genres)
    all_animes = []
    genres_map = {}
    
    # Ordenar resultados por data de modificação (mais recente primeiro)
    results.sort(key=lambda x: x['last_updated'], reverse=True)

    for data in results:
        item = data['summary']
        
        # Resumo para listas (Leve)
        summary = {
            "title": item['title_english'] or item['title'],
            "slug": item['slug'],
            "image": item['image'],
            "score": item['score'],
            "type": item['type']
        }
        all_animes.append(summary)

        # Agrupar por Gênero
        for g in data['genres']:
            g_name = g['name']
            g_slug = sanitize_filename(g_name.lower().replace(" ", "-"))
            
            if g_slug not in genres_map:
                genres_map[g_slug] = {
                    "name": g_name, 
                    "slug": g_slug, 
                    "count": 0, 
                    "animes": []
                }
            
            genres_map[g_slug]["animes"].append(summary)
            genres_map[g_slug]["count"] += 1

    # Salvar 'all.json'
    save_json(os.path.join(API_ANIMES_DIR, "all.json"), all_animes)

    # --- NOVO: Salvar 'new_animes.json' (Top 20 Recentes) ---
    print(">>> Gerando lista de novos animes...")
    new_animes_list = []
    for data in results[:20]:
        item = data['summary']
        new_animes_list.append({
            "title": item['title_english'] or item['title'],
            "slug": item['slug'],
            "image": item['image'],
            "score": item['score'],
            "type": item['type'],
            "updated_at": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['last_updated']))
        })
    save_json(os.path.join(API_ANIMES_DIR, "new_animes.json"), new_animes_list)

    # --- NOVO: Salvar 'latest_episodes.json' (Top 50 Episódios Recentes) ---
    print(">>> Gerando lista de últimos episódios...")
    latest_episodes_list = []
    for data in results[:50]:
        if data['latest_episode']:
            item = data['summary']
            ep = data['latest_episode']
            latest_episodes_list.append({
                "anime_title": item['title_english'] or item['title'],
                "anime_slug": item['slug'],
                "anime_image": item['image'],
                "episode_number": ep['numero'],
                "episode_title": ep.get('nome', f"Episódio {ep['numero']}"),
                "episode_url": ep['url'],
                "type": item['type'],
                "created_at": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data['last_updated']))
            })
    save_json(os.path.join(API_ANIMES_DIR, "latest_episodes.json"), latest_episodes_list)

    # Salvar arquivos de cada gênero e criar lista master
    lista_generos_simples = []
    
    print(">>> Salvando arquivos de gêneros...")
    for g_slug, content in genres_map.items():
        # Salva o arquivo detalhado do gênero (ex: action.json com lista de animes)
        save_json(os.path.join(API_GENRES_DIR, f"{g_slug}.json"), content)
        
        # Adiciona à lista simples
        lista_generos_simples.append({
            "name": content['name'],
            "slug": content['slug'],
            "count": content['count']
        })

    # Ordenar e salvar 'list.json'
    lista_generos_simples.sort(key=lambda x: x['name'])
    save_json(os.path.join(API_GENRES_DIR, "list.json"), lista_generos_simples)

    print(f"\n=== SUCESSO! API GERADA EM '{OUTPUT_API_DIR}' ===")
    print(f"- Animes processados: {len(results)}")
    print(f"- Gêneros catalogados: {len(lista_generos_simples)}")
    print(f"- Animes vazios ignorados: {total - len(results)}")

if __name__ == "__main__":
    main()