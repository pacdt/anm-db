import sys
import os
import json
import time
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs
import requests
from urllib.parse import parse_qsl, quote, unquote

# Importa o resolver
sys.path.append(os.path.join(os.path.dirname(__file__), 'resources', 'lib'))
import resolver

# --- CONSTANTES ---
URL_BASE = sys.argv[0]
HANDLE = int(sys.argv[1])
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# GitHub Config
GITHUB_USER = "pacdt"
GITHUB_REPO = "anm-db"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"

# Pastas de Dados Locais (Userdata)
PROFILE_PATH = xbmc.translatePath('special://profile/addon_data/plugin.video.meuanime')
CACHE_PATH = os.path.join(PROFILE_PATH, 'cache')
HISTORY_FILE = os.path.join(PROFILE_PATH, 'history.json')
SEARCH_FILE = os.path.join(PROFILE_PATH, 'search_history.json')

# Tempo de Cache em segundos (3600 = 1 hora)
CACHE_TTL = 3600 

# Garante que as pastas existem
if not xbmcvfs.exists(PROFILE_PATH):
    xbmcvfs.mkdir(PROFILE_PATH)
if not xbmcvfs.exists(CACHE_PATH):
    xbmcvfs.mkdir(CACHE_PATH)

# --- GERENCIADOR DE DADOS LOCAIS ---

def carregar_json_local(caminho, padrao=None):
    if xbmcvfs.exists(caminho):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return padrao if padrao is not None else {}

def salvar_json_local(caminho, dados):
    try:
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        xbmc.log(f"[MeusAnimes] Erro ao salvar {caminho}: {e}", xbmc.LOGERROR)

def get_cached_request(url):
    """Faz requisição GET com cache local baseado no hash da URL"""
    import hashlib
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    cache_file = os.path.join(CACHE_PATH, f"{url_hash}.json")
    
    # Verifica se cache é válido (existe e não expirou)
    if xbmcvfs.exists(cache_file):
        stat = xbmcvfs.Stat(cache_file)
        if (time.time() - stat.st_mtime()) < CACHE_TTL:
            xbmc.log(f"[MeusAnimes] Usando Cache: {url}", xbmc.LOGINFO)
            return carregar_json_local(cache_file)

    # Se não tem cache ou venceu, baixa da internet
    xbmc.log(f"[MeusAnimes] Baixando: {url}", xbmc.LOGINFO)
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            dados = r.json()
            salvar_json_local(cache_file, dados) # Salva no cache
            return dados
    except: pass
    return None

def adicionar_ao_historico_busca(termo):
    historico = carregar_json_local(SEARCH_FILE, [])
    if termo in historico:
        historico.remove(termo)
    historico.insert(0, termo)
    historico = historico[:20] # Mantém apenas os últimos 20
    salvar_json_local(SEARCH_FILE, historico)

def limpar_historico_busca():
    salvar_json_local(SEARCH_FILE, [])
    xbmcgui.Dialog().notification('Sucesso', 'Histórico de busca limpo.', xbmcgui.NOTIFICATION_INFO)

def registrar_assistido(anime_nome, anime_img, url_json_ep, ep_num, ep_nome):
    """Salva o progresso do anime no histórico"""
    hist = carregar_json_local(HISTORY_FILE, {})
    
    # Usa a URL do JSON como ID único
    anime_id = url_json_ep
    
    hist[anime_id] = {
        "nome": anime_nome,
        "imagem": anime_img,
        "url_json": url_json_ep,
        "ultimo_ep": ep_num,
        "ultimo_ep_nome": ep_nome,
        "timestamp": time.time()
    }
    salvar_json_local(HISTORY_FILE, hist)

# --- UTILITÁRIOS VISUAIS ---

def construir_url(query):
    return URL_BASE + '?' + query

def formatar_label_rico(nome, meta):
    """Cria um título informativo: Nome - ★ 9.0 - Ação"""
    if not meta: return nome
    
    extras = []
    if meta.get('nota_media'):
        extras.append(f"[COLOR yellow]★ {meta['nota_media']}[/COLOR]")
    
    if meta.get('generos'):
        # Pega só os 2 primeiros gêneros para não poluir
        gens = meta['generos'][:2]
        extras.append(f"[COLOR gray]{', '.join(gens)}[/COLOR]")
    
    if extras:
        return f"{nome}   {'  '.join(extras)}"
    return nome

# --- MENUS ---

def menu_principal():
    # 1. Busca
    li_busca = xbmcgui.ListItem(label='[B] Pesquisar / Buscar[/B]')
    li_busca.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(HANDLE, construir_url('mode=busca_menu'), li_busca, isFolder=True)

    # 2. Histórico
    li_hist = xbmcgui.ListItem(label='[B] Meu Histórico (Continuar assistindo)[/B]')
    li_hist.setArt({'icon': 'DefaultVideoPlaylists.png'})
    xbmcplugin.addDirectoryItem(HANDLE, construir_url('mode=historico'), li_hist, isFolder=True)

    # 3. Categorias (Apenas Séries)
    menus = [
        ('Séries Dubladas', 'Dublados'),
        ('Séries Legendadas', 'Legendados')
    ]

    for label, cat in menus:
        li = xbmcgui.ListItem(label=label)
        li.setInfo('video', {'plot': f'Lista de {label}'})
        xbmcplugin.addDirectoryItem(HANDLE, construir_url(f'mode=listar&categoria={cat}'), li, isFolder=True)

    xbmcplugin.endOfDirectory(HANDLE)

def menu_historico():
    hist = carregar_json_local(HISTORY_FILE, {})
    
    # Ordena por timestamp (mais recente primeiro)
    itens_ordenados = sorted(hist.values(), key=lambda x: x['timestamp'], reverse=True)
    
    if not itens_ordenados:
        li = xbmcgui.ListItem(label="Nenhum histórico encontrado")
        xbmcplugin.addDirectoryItem(HANDLE, construir_url(""), li, isFolder=False)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    # Opção de limpar
    li_limpar = xbmcgui.ListItem(label="[COLOR red][Apagar Histórico][/COLOR]")
    xbmcplugin.addDirectoryItem(HANDLE, construir_url("mode=limpar_hist"), li_limpar, isFolder=False)

    for item in itens_ordenados:
        nome = item['nome']
        ultimo = f" (Parou no Ep {item['ultimo_ep']})"
        label = f"{nome} {ultimo}"
        
        li = xbmcgui.ListItem(label=label)
        li.setArt({'thumb': item['imagem'], 'icon': item['imagem']})
        li.setInfo('video', {'title': nome, 'plot': f'Último episódio assistido: {item["ultimo_ep_nome"]}'})
        
        # Ao clicar, abre a lista de episódios daquele anime
        url = construir_url(f"mode=episodios&url_json={quote(item['url_json'])}")
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
        
    xbmcplugin.endOfDirectory(HANDLE)

def menu_busca():
    # 1. Nova Busca
    li_nova = xbmcgui.ListItem(label="[ Nova Pesquisa ]")
    li_nova.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(HANDLE, construir_url('mode=fazer_busca'), li_nova, isFolder=True)
    
    # 2. Histórico de Busca
    historico = carregar_json_local(SEARCH_FILE, [])
    
    if historico:
        li_limpar = xbmcgui.ListItem(label="[ Limpar Histórico de Busca ]")
        xbmcplugin.addDirectoryItem(HANDLE, construir_url('mode=limpar_busca'), li_limpar, isFolder=False)

        for termo in historico:
            li = xbmcgui.ListItem(label=f"Buscar: {termo}")
            xbmcplugin.addDirectoryItem(HANDLE, construir_url(f"mode=listar&busca={quote(termo)}"), li, isFolder=True)

    xbmcplugin.endOfDirectory(HANDLE)

def listar_animes(categoria=None, termo_busca=None):
    # Determina quais listas baixar (apenas séries agora)
    if termo_busca:
        categorias = ['Dublados', 'Legendados']
    else:
        categorias = [categoria]
    
    todos_itens = []
    
    for cat in categorias:
        if cat == 'Dublados': arq = 'animes_dublados.json'
        elif cat == 'Legendados': arq = 'animes_legendados.json'
        else: continue
            
        url_lista = f"{GITHUB_RAW_BASE}/{arq}"
        
        # USA O CACHE
        lista = get_cached_request(url_lista)
        
        if lista:
            for item in lista:
                item['_cat_origem'] = cat
                todos_itens.append(item)

    # Filtragem por busca
    if termo_busca:
        termo_busca = termo_busca.lower()
        todos_itens = [x for x in todos_itens if termo_busca in x.get('nome', '').lower()]

    # Ordenação
    todos_itens.sort(key=lambda x: x.get('nome', ''))

    # Renderização
    for item in todos_itens:
        nome = item.get('nome')
        img = item.get('imagem', '')
        link = item.get('link', '')
        cat_origem = item.get('_cat_origem')
        
        # Extrai Slug
        if '/animes/' in link: slug = link.split('/animes/')[-1]
        else: slug = link.rstrip('/').split('/')[-1]
        slug = slug.replace('-todos-os-episodios', '')

        # Define caminho do JSON (agora simplificado, sem filmes)
        subpasta = cat_origem # Dublados ou Legendados
        
        url_json_ep = f"{GITHUB_RAW_BASE}/Episodios/{subpasta}/{slug}.json"
        
        # Formata o nome com metadados se disponíveis
        meta = item.get('metadata_completo') 
        label_formatado = formatar_label_rico(nome, meta)
        
        li = xbmcgui.ListItem(label=label_formatado)
        li.setArt({'thumb': img, 'icon': img, 'poster': img})
        
        info = {'title': nome, 'mediatype': 'video'}
        if meta:
            info['plot'] = meta.get('sinopse', '')
            info['rating'] = meta.get('nota_media', 0)
            info['genre'] = ", ".join(meta.get('generos', []))
            info['year'] = meta.get('ano')
            
        li.setInfo('video', info)
        
        url = construir_url(f"mode=episodios&url_json={quote(url_json_ep)}")
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)

    xbmcplugin.endOfDirectory(HANDLE)

def listar_episodios(url_json):
    # Usa cache para os episódios também
    dados = get_cached_request(url_json)
    
    if not dados:
        xbmcgui.Dialog().notification('Erro', 'Conteúdo não encontrado.', xbmcgui.NOTIFICATION_ERROR)
        return

    episodios = dados.get('episodios', [])
    nome_anime = dados.get('nome', 'Anime')
    
    meta = dados.get('metadata_completo', {})
    img_anime = meta.get('imagem_capa') or dados.get('imagem', '')
    sinopse = meta.get('sinopse', '')
    generos = ", ".join(meta.get('generos', []))
    
    # Verifica histórico para marcar assistidos
    hist = carregar_json_local(HISTORY_FILE, {})
    ultimo_ep_visto = 0
    if url_json in hist:
        ultimo_ep_visto = hist[url_json]['ultimo_ep']

    for ep in episodios:
        num = ep['numero']
        link = ep['url']
        ep_nome = ep.get('nome', '')
        
        num_fmt = "{:02d}".format(num)
        titulo = f"EP {num_fmt}"
        if ep_nome: titulo += f" - {ep_nome}"
        
        # Check visual (✔) para episódios já vistos
        if num <= ultimo_ep_visto:
            titulo = f"[COLOR green]✔[/COLOR] {titulo}"

        li = xbmcgui.ListItem(label=titulo)
        
        info = {
            'title': titulo,
            'tvshowtitle': nome_anime,
            'episode': num,
            'plot': sinopse,
            'genre': generos,
            'mediatype': 'episode'
        }
        
        li.setInfo('video', info)
        li.setArt({'thumb': img_anime, 'icon': img_anime})
        li.setProperty('IsPlayable', 'true')
        
        # Prepara argumentos para play e salvar histórico
        args_play = {
            "mode": "play",
            "url": link,
            "anime": nome_anime,
            "img": img_anime,
            "json": url_json,
            "ep_n": str(num),
            "ep_t": ep_nome
        }
        
        q_str = "&".join([f"{k}={quote(v)}" for k, v in args_play.items()])
        url_play = URL_BASE + '?' + q_str
        
        xbmcplugin.addDirectoryItem(HANDLE, url_play, li, isFolder=False)
        
    xbmcplugin.endOfDirectory(HANDLE)

def tocar_video(params):
    url_bruta = params.get('url')
    
    # 1. Salva no Histórico
    try:
        registrar_assistido(
            anime_nome=params.get('anime'),
            anime_img=params.get('img'),
            url_json_ep=params.get('json'),
            ep_num=int(params.get('ep_n', 0)),
            ep_nome=params.get('ep_t', '')
        )
    except Exception as e:
        xbmc.log(f"Erro ao salvar histórico: {e}", xbmc.LOGERROR)

    # 2. Resolve Link
    url_final = resolver.resolver_link(url_bruta, user_agent=USER_AGENT)
    
    if url_final:
        # Headers para Google/Blogger
        if 'googlevideo.com' in url_final or 'blogger.com' in url_bruta:
            headers = f"User-Agent={quote(USER_AGENT)}&Referer={quote('https://www.blogger.com/')}"
            url_final = f"{url_final}|{headers}"
            
        li = xbmcgui.ListItem(path=url_final)
        li.setProperty('IsPlayable', 'true')
        xbmcplugin.setResolvedUrl(HANDLE, True, listitem=li)
    else:
        xbmcgui.Dialog().notification('Erro', 'Link indisponível.', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(HANDLE, False, listitem=None)

# --- ROTEAMENTO ---
params = dict(parse_qsl(sys.argv[2][1:]))
mode = params.get('mode')

if mode is None:
    menu_principal()

elif mode == 'busca_menu':
    menu_busca()

elif mode == 'fazer_busca':
    kb = xbmc.Keyboard('', 'Pesquisar Anime')
    kb.doModal()
    if kb.isConfirmed() and kb.getText():
        termo = kb.getText()
        adicionar_ao_historico_busca(termo)
        listar_animes(termo_busca=termo)

elif mode == 'limpar_busca':
    limpar_historico_busca()
    xbmc.executebuiltin('Container.Refresh')

elif mode == 'listar':
    cat = params.get('categoria')
    busca = params.get('busca')
    listar_animes(categoria=cat, termo_busca=busca)

elif mode == 'episodios':
    url = unquote(params.get('url_json'))
    listar_episodios(url)

elif mode == 'play':
    tocar_video(params)

elif mode == 'historico':
    menu_historico()

elif mode == 'limpar_hist':
    salvar_json_local(HISTORY_FILE, {})
    xbmc.executebuiltin('Container.Refresh')