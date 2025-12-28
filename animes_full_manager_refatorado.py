import json
import os
import requests
import time
import re
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Arquivos e Pastas
ARQUIVO_LISTA_DUBLADOS = 'animes_dublados.json'
ARQUIVO_LISTA_LEGENDADOS = 'animes_legendados.json'
STATUS_FILE = 'status.json'
FOLDER_LOGS = 'logs_atualizacoes'  # Pasta para os logs JSON
FOLDER_DUBLADOS = os.path.join('Episodios', 'Dublados')
FOLDER_LEGENDADOS = os.path.join('Episodios', 'Legendados')

# Configurações de Execução
PAGINAS_DUBLADOS = 30
PAGINAS_LEGENDADOS = 190 # Atualizado conforme pedido
MAX_WORKERS = 3 
INTERVALO_HORAS = 24

# Controles
MAX_RETRIES = 5
RETRY_DELAY = 3
MAX_ERROS_SEQUENCIAIS = 10 
DELAY_JIKAN = 1.5 

# Status Global e Bloqueios
jikan_lock = Lock()
status_lock = Lock()
log_lock = Lock()

# Variável para armazenar atualizações do ciclo atual
animes_atualizados_ciclo = []

# --- UTILITÁRIOS DE SISTEMA ---

def executar_comando_git(mensagem):
    """Executa comandos git para commit e push"""
    try:
        print(f"\n[GIT] Iniciando processo de commit: {mensagem}")
        # Adiciona tudo
        subprocess.run(["git", "add", "."], check=True)
        # Commit
        subprocess.run(["git", "commit", "-m", mensagem], check=True)
        # Push
        subprocess.run(["git", "push"], check=True)
        print("[GIT] Push realizado com sucesso!")
    except subprocess.CalledProcessError as e:
        print(f"[GIT] Erro ao executar git: {e}")
    except Exception as e:
        print(f"[GIT] Erro inesperado: {e}")

def limpar_arquivos_listas():
    """Remove os arquivos de lista para forçar uma nova varredura limpa"""
    for arq in [ARQUIVO_LISTA_DUBLADOS, ARQUIVO_LISTA_LEGENDADOS]:
        if os.path.exists(arq):
            try:
                os.remove(arq)
                print(f"[SISTEMA] Arquivo removido para nova varredura: {arq}")
            except Exception as e:
                print(f"[SISTEMA] Erro ao remover {arq}: {e}")

def gerar_log_ciclo():
    """Gera o arquivo JSON com as atualizações encontradas neste ciclo"""
    if not animes_atualizados_ciclo:
        print("[LOG] Nenhuma atualização encontrada neste ciclo.")
        return

    if not os.path.exists(FOLDER_LOGS):
        os.makedirs(FOLDER_LOGS)

    data_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_arquivo = f"update_{data_str}.json"
    caminho_arquivo = os.path.join(FOLDER_LOGS, nome_arquivo)

    dados_log = {
        "data_verificacao": data_str,
        "total_animes_atualizados": len(animes_atualizados_ciclo),
        "atualizacoes": animes_atualizados_ciclo
    }

    try:
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados_log, f, ensure_ascii=False, indent=4)
        print(f"[LOG] Log de atualizações salvo em: {caminho_arquivo}")
    except Exception as e:
        print(f"[LOG] Erro ao salvar log: {e}")

# --- UTILITÁRIOS GERAIS ---

def atualizar_status(anime_nome, ep_atual, indice, total, status_msg, tipo="Geral"):
    with status_lock:
        dados = {
            "current": {
                "nome": anime_nome,
                "tipo": tipo,
                "episodio": ep_atual,
                "indice": indice,
                "total": total,
                "status": status_msg
            },
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            with open(STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(dados, f, ensure_ascii=False)
        except Exception as e:
            print(f"Erro status: {e}")

def extrair_slug(url_anime):
    if '/animes/' in url_anime:
        slug = url_anime.split('/animes/')[-1]
    else:
        slug = url_anime.rstrip('/').split('/')[-1]
    slug = slug.replace('-todos-os-episodios', '')
    return slug

def criar_pastas():
    for p in [FOLDER_DUBLADOS, FOLDER_LEGENDADOS, FOLDER_LOGS]:
        if not os.path.exists(p): os.makedirs(p)

def limpar_nome_para_busca(nome):
    return re.sub(r'\s*\((Dublado|Legendado|TV|OVA)\)', '', nome, flags=re.IGNORECASE).strip()

def calcular_similaridade(a, b):
    if not a or not b: return 0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# --- MÓDULO 1: SCRAPING DA LISTA ---

def extrair_animes_da_pagina(url):
    animes = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 200: return []
        soup = BeautifulSoup(response.content, 'html.parser')
        for link in soup.find_all('a', href=True):
            h3 = link.find('h3', class_='animeTitle')
            if h3:
                nome = h3.get_text(strip=True)
                href = link['href']
                img = link.find('img')
                src = img.get('data-src') or img.get('src') if img else None
                if '/animes/' in href and nome:
                    item = {'nome': nome, 'link': href}
                    if src: item['imagem'] = src
                    animes.append(item)
    except Exception as e:
        print(f"Erro URL {url}: {e}")
    return animes

def buscar_lista_animes(tipo, total_paginas, arquivo_saida):
    # Como rodamos em loop e deletamos o arquivo antes, aqui sempre será uma busca nova
    # Usamos um dicionário para garantir unicidade pelo Link (slug)
    animes_unicos = {}
    
    base = f"{BASE_URL_SITE}/lista-de-animes-{tipo}s"
    print(f"\n>>> Mapeando lista: {tipo.upper()}...")
    
    for p in range(1, total_paginas + 1):
        url = base if p == 1 else f"{base}/{p}"
        print(f"Lendo página {p}/{total_paginas}...")
        animes_pagina = extrair_animes_da_pagina(url)
        
        for anime in animes_pagina:
            slug = extrair_slug(anime['link'])
            if slug not in animes_unicos:
                animes_unicos[slug] = anime
        
        if p % 5 == 0: 
            atualizar_status(f"Lista {tipo}", len(animes_unicos), p, total_paginas, "Mapeando...", tipo)
            time.sleep(0.5)

    lista_final = list(animes_unicos.values())
    
    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        json.dump(lista_final, f, ensure_ascii=False, indent=2)
    
    return lista_final

# --- MÓDULO 2: API JIKAN ---

def buscar_metadados_jikan(nome_anime):
    nome_pesquisa = limpar_nome_para_busca(nome_anime)
    params = {'q': nome_pesquisa, 'limit': 5}
    
    with jikan_lock:
        try:
            time.sleep(DELAY_JIKAN)
            response = requests.get(BASE_API_JIKAN_ANIME, params=params, headers=HEADERS, timeout=10)
            
            if response.status_code == 429:
                time.sleep(5)
                return None 
            if response.status_code != 200: return None

            data = response.json().get('data', [])
            if not data: return None

            melhor_match = None
            maior_score = 0
            for anime in data:
                if anime.get('rating') == 'Rx - Hentai': continue
                titulos = [anime.get('title'), anime.get('title_english'), anime.get('title_japanese')]
                score = max([calcular_similaridade(nome_pesquisa, t) for t in titulos if t])
                if score > maior_score:
                    maior_score = score
                    melhor_match = anime

            if melhor_match and maior_score > 0.4:
                return {
                    "titulo_oficial": melhor_match.get('title'),
                    "titulo_ingles": melhor_match.get('title_english'),
                    "generos": [g['name'] for g in melhor_match.get('genres', [])],
                    "classificacao": melhor_match.get('rating'),
                    "popularidade": melhor_match.get('popularity'),
                    "nota_media": melhor_match.get('score'),
                    "sinopse": melhor_match.get('synopsis'),
                    "ano": melhor_match.get('year'),
                    "status": melhor_match.get('status'),
                    "imagem_capa": melhor_match.get('images', {}).get('jpg', {}).get('image_url'),
                    "id_mal": melhor_match.get('mal_id')
                }
        except Exception as e:
            print(f"Erro Jikan: {e}")
    return None

def buscar_nomes_episodios_jikan(mal_id):
    url_base = BASE_API_JIKAN_EPISODIOS.format(id=mal_id)
    nomes_episodios = {}
    pagina = 1
    
    with jikan_lock:
        while True:
            url = f"{url_base}?page={pagina}"
            try:
                time.sleep(DELAY_JIKAN)
                response = requests.get(url, headers=HEADERS, timeout=10)
                
                if response.status_code == 429:
                    time.sleep(5)
                    continue
                if response.status_code != 200: break

                data = response.json()
                for ep in data.get('data', []):
                    if ep.get('mal_id') and ep.get('title'):
                        nomes_episodios[str(ep.get('mal_id'))] = ep.get('title')
                
                if not data.get('pagination', {}).get('has_next_page'): break
                pagina += 1
            except: break
    return nomes_episodios

# --- MÓDULO 3: PROCESSAMENTO INDIVIDUAL ---

def buscar_link_video_api(url_api):
    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(url_api, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('response', {}).get('status') == '500': return None, False
                link = data.get('token') or (data['data'][-1]['src'] if data.get('data') else None)
                return link, True
            elif r.status_code == 404:
                return None, False
            time.sleep(RETRY_DELAY)
        except: time.sleep(RETRY_DELAY)
    return None, True

def processar_anime_individual(anime, pasta_destino, indice, total, tipo_label):
    nome = anime['nome']
    slug = extrair_slug(anime['link'])
    arquivo_path = os.path.join(pasta_destino, f"{slug}.json")
    
    print(f"[{indice}/{total}] ⏳ Verificando: {nome}...")

    dados_anime = {
        "nome": nome, "slug": slug, "imagem": anime.get('imagem', ''), 
        "total_episodios": 0, "episodios": []
    }
    
    ja_existe = False
    tem_metadata_completo = False
    
    if os.path.exists(arquivo_path):
        try:
            with open(arquivo_path, 'r', encoding='utf-8') as f:
                dados_existentes = json.load(f)
                meta = dados_existentes.get('metadata_completo', {})
                if meta and meta.get('id_mal'):
                    tem_metadata_completo = True
                
                if 'nomes_episodios' in dados_existentes:
                    dados_anime['nomes_episodios'] = dados_existentes['nomes_episodios']
                
                dados_anime.update(dados_existentes)
                ja_existe = True
        except: pass

    ultimo_ep = dados_anime.get('total_episodios', 0)
    
    # Busca de Novos Episódios
    prox_ep = ultimo_ep + 1
    novos_encontrados_nesta_rodada = []
    erros_seq = 0
    
    while True:
        url_api = f"{BASE_URL_VIDEO}/{slug}/{prox_ep}"
        link_final, continuar = buscar_link_video_api(url_api)
        
        if not continuar: break 
        
        if link_final:
            if not any(ep['numero'] == prox_ep for ep in dados_anime['episodios']):
                novo_ep_obj = {"numero": prox_ep, "url": link_final}
                dados_anime['episodios'].append(novo_ep_obj)
                novos_encontrados_nesta_rodada.append(novo_ep_obj)
                print(f"   --> {nome}: Novo Ep {prox_ep}")
            erros_seq = 0
        else:
            erros_seq += 1
            if erros_seq >= MAX_ERROS_SEQUENCIAIS: break
        
        prox_ep += 1

    dados_anime['episodios'].sort(key=lambda x: x['numero'])
    if dados_anime['episodios']:
        dados_anime['total_episodios'] = dados_anime['episodios'][-1]['numero']

    # Metadados Jikan
    alterado_jikan = False
    mal_id = dados_anime.get('metadata_completo', {}).get('id_mal')
    
    if not tem_metadata_completo and not mal_id:
        meta_status = dados_anime.get('metadata_completo', {}).get('erro')
        if meta_status != "Nao encontrado":
            meta = buscar_metadados_jikan(nome)
            if meta:
                dados_anime['metadata_completo'] = meta
                dados_anime['generos'] = meta.get('generos')
                dados_anime['nota'] = meta.get('nota_media')
                dados_anime['ano'] = meta.get('ano')
                mal_id = meta.get('id_mal')
                alterado_jikan = True
            else:
                dados_anime['metadata_completo'] = {"erro": "Nao encontrado"}
                alterado_jikan = True

    # Nomes dos Episódios
    novos_count = len(novos_encontrados_nesta_rodada)
    if mal_id and (novos_count > 0 or ('nomes_episodios' not in dados_anime and len(dados_anime['episodios']) > 0)):
        todos_tem_nome = all('nome' in ep for ep in dados_anime['episodios'])
        if not todos_tem_nome:
            nomes_eps = buscar_nomes_episodios_jikan(mal_id)
            if nomes_eps:
                dados_anime['nomes_episodios'] = nomes_eps
                alterado_jikan = True

    # Integrar nomes aos episódios novos
    nomes_disp = dados_anime.get('nomes_episodios', {})
    
    # Atualiza nomes no objeto principal
    if nomes_disp:
        for ep in dados_anime['episodios']:
            s_num = str(ep['numero'])
            if s_num in nomes_disp and 'nome' not in ep:
                ep['nome'] = nomes_disp[s_num]
                alterado_jikan = True
    
    # Atualiza nomes na lista de novos (para o log)
    if novos_count > 0:
        for ep_novo in novos_encontrados_nesta_rodada:
            s_num = str(ep_novo['numero'])
            if s_num in nomes_disp:
                ep_novo['nome'] = nomes_disp[s_num]

        # Adiciona ao LOG GLOBAL
        with log_lock:
            animes_atualizados_ciclo.append({
                "nome": nome,
                "poster": dados_anime.get('imagem') or dados_anime.get('metadata_completo', {}).get('imagem_capa'),
                "novos_episodios": novos_encontrados_nesta_rodada,
                "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

    # Limpeza final
    if 'nomes_episodios' in dados_anime:
        del dados_anime['nomes_episodios']

    # Salvar JSON
    if novos_count > 0 or alterado_jikan or not ja_existe:
        with open(arquivo_path, 'w', encoding='utf-8') as f:
            json.dump(dados_anime, f, indent=4, ensure_ascii=False)
    
    return nome

# --- GERENCIADOR DE THREADS ---

def processar_lista_paralela(lista_animes, pasta, tipo_label):
    total = len(lista_animes)
    print(f"\n{'='*60}")
    print(f"Iniciando Threads para {tipo_label} ({MAX_WORKERS} workers)...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(processar_anime_individual, anime, pasta, i, total, tipo_label): anime['nome']
            for i, anime in enumerate(lista_animes, 1)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"❌ Erro thread: {e}")

# --- LOOP PRINCIPAL (SERVIDOR) ---

def main_loop():
    print("=== SERVER: ANIME MANAGER STARTING ===")
    
    while True:
        inicio_ciclo = datetime.now()
        print(f"\n\n>>> INICIANDO CICLO: {inicio_ciclo.strftime('%d/%m/%Y %H:%M:%S')}")
        
        # 0. Limpar variáveis globais do ciclo anterior
        global animes_atualizados_ciclo
        animes_atualizados_ciclo = []
        
        # 1. Preparar pastas e limpar arquivos antigos
        criar_pastas()
        limpar_arquivos_listas()
        
        # 2. Processar Dublados
        lista_dub = buscar_lista_animes('dublado', PAGINAS_DUBLADOS, ARQUIVO_LISTA_DUBLADOS)
        processar_lista_paralela(lista_dub, FOLDER_DUBLADOS, "Dublado")
        
        # 3. Processar Legendados
        lista_leg = buscar_lista_animes('legendado', PAGINAS_LEGENDADOS, ARQUIVO_LISTA_LEGENDADOS)
        processar_lista_paralela(lista_leg, FOLDER_LEGENDADOS, "Legendado")
        
        # 4. Gerar Log de Atualizações
        gerar_log_ciclo()
        
        # 5. Git Commit & Push
        fim_ciclo = datetime.now()
        msg_commit = f"Auto Update: {fim_ciclo.strftime('%Y-%m-%d %H:%M')}"
        executar_comando_git(msg_commit)
        
        # 6. Aguardar próximo ciclo
        print(f"\n>>> CICLO FINALIZADO ÀS {fim_ciclo.strftime('%H:%M:%S')}")
        print(f">>> AGUARDANDO {INTERVALO_HORAS} HORAS...")
        
        segundos_espera = INTERVALO_HORAS * 3600
        time.sleep(segundos_espera)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nServidor parado manualmente.")