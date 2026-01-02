import json
import os
import requests
import time
import re
import random
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# --- CONFIGURAÇÕES GERAIS ---
BASE_URL_SITE = "https://animefire.plus"
BASE_URL_VIDEO = "https://animefire.plus/video"

# Endpoints da API Jikan
BASE_API_JIKAN_ANIME = "https://api.jikan.moe/v4/anime"
BASE_API_JIKAN_EPISODIOS = "https://api.jikan.moe/v4/anime/{id}/episodes"

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

# Estrutura de Pastas e Arquivos
ARQUIVO_LISTA_DUBLADOS = 'animes_dublados.json'
ARQUIVO_LISTA_LEGENDADOS = 'animes_legendados.json'
FOLDER_LOGS = 'logs_atualizacoes'
FOLDER_DUBLADOS = os.path.join('Episodios', 'Dublados')
FOLDER_LEGENDADOS = os.path.join('Episodios', 'Legendados')

# Configurações de Execução
PAGINAS_DUBLADOS = 30
PAGINAS_LEGENDADOS = 190
MAX_WORKERS_SCRAPER = 50 
INTERVALO_HORAS = 24

# Controles de Erro e Delay
MAX_RETRIES = 5
MAX_ERROS_SEQUENCIAIS = 10 
TIMEOUT_REQUEST = 5

# Bloqueios (Locks) para Threading
log_lock = Lock()
animes_atualizados_ciclo = []

# --- UTILITÁRIOS ---

def criar_pastas_necessarias():
    dirs = [
        FOLDER_DUBLADOS, FOLDER_LEGENDADOS, FOLDER_LOGS
    ]
    for p in dirs:
        if not os.path.exists(p): os.makedirs(p)

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



# --- SCRAPER ---

def extrair_animes_da_pagina(url):
    animes = []
    try:
        response = requests.get(url, headers=get_random_header(), timeout=TIMEOUT_REQUEST)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            for link in soup.find_all('a', href=True):
                h3 = link.find('h3', class_='animeTitle')
                if h3 and '/animes/' in link['href']:
                    img = link.find('img')
                    src = img.get('data-src') or img.get('src') if img else None
                    animes.append({'nome': h3.get_text(strip=True), 'link': link['href'], 'imagem': src})
    except: pass
    return animes

def buscar_lista_animes(tipo, paginas, arquivo_saida):
    animes_unicos = {}
    base = f"{BASE_URL_SITE}/lista-de-animes-{tipo}s"
    print(f"\n>>> Mapeando lista: {tipo.upper()}...")
    
    for p in range(1, paginas + 1):
        url = base if p == 1 else f"{base}/{p}"
        if p % 5 == 0: print(f"Lendo pg {p}/{paginas}")
        for anime in extrair_animes_da_pagina(url):
            slug = extrair_slug(anime['link'])
            if slug not in animes_unicos: animes_unicos[slug] = anime
        time.sleep(0.2)
        
    lista = list(animes_unicos.values())
    save_json(arquivo_saida, lista)
    return lista

def buscar_link_video(url_api):
    for _ in range(2):
        try:
            r = requests.get(url_api, headers=get_random_header(), timeout=TIMEOUT_REQUEST)
            if r.status_code == 200:
                d = r.json()
                link = d.get('token') or (d['data'][-1]['src'] if d.get('data') else None)
                return link, True
            if r.status_code == 404: return None, False
        except: time.sleep(1)
    return None, True

def processar_anime(anime, pasta, indice, total):
    nome, slug = anime['nome'], extrair_slug(anime['link'])
    path = os.path.join(pasta, f"{slug}.json")
    
    if indice % 20 == 0: print(f"[{indice}/{total}] Processando: {nome}")
    
    dados = {"nome": nome, "slug": slug, "imagem": anime.get('imagem'), "episodios": []}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                dados.update(json.load(f))
        except json.JSONDecodeError:
            print(f"  [AVISO] Arquivo JSON corrompido para {nome}, recriando do zero.")
            # Se o JSON estiver corrompido, `dados` já está resetado para o padrão
            pass
            
    # Lógica de scraping de episódios
    ultimo = dados['episodios'][-1]['numero'] if dados.get('episodios') else 0
    prox = ultimo + 1
    novos = []
    
    erros = 0
    while erros < MAX_ERROS_SEQUENCIAIS:
        link, continuar = buscar_link_video(f"{BASE_URL_VIDEO}/{slug}/{prox}")
        if not continuar: break
        if link:
            obj = {"numero": prox, "url": link}
            dados['episodios'].append(obj)
            novos.append(obj)
            erros = 0
        else:
            erros += 1
        prox += 1
        
    if novos:
        dados['episodios'].sort(key=lambda x: x['numero'])
        save_json(path, dados)
        with log_lock:
            animes_atualizados_ciclo.append(nome)

def rodar_scraper(lista, pasta):
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_SCRAPER) as exe:
        futures = {exe.submit(processar_anime, a, pasta, i, len(lista)): a for i, a in enumerate(lista, 1)}
        for f in as_completed(futures): f.result()



# --- MAIN LOOP ---

def main():
    print("=== SERVER STARTED ===")
    while True:
        try:
            print(f"\n--- INÍCIO CICLO: {datetime.now()} ---")
            global animes_atualizados_ciclo
            animes_atualizados_ciclo = []
            
            criar_pastas_necessarias()
            
            # 1. Scrapers
            l_dub = buscar_lista_animes('dublado', PAGINAS_DUBLADOS, ARQUIVO_LISTA_DUBLADOS)
            rodar_scraper(l_dub, FOLDER_DUBLADOS)
            
            l_leg = buscar_lista_animes('legendado', PAGINAS_LEGENDADOS, ARQUIVO_LISTA_LEGENDADOS)
            rodar_scraper(l_leg, FOLDER_LEGENDADOS)
            
            print(f"--- FIM CICLO. ---")
            break
            
        except Exception as e:
            print(f"ERRO CRÍTICO NO MAIN: {e}")
            time.sleep(600)

if __name__ == "__main__":
    main()