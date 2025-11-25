import requests
import json
import xbmc

# --- LÓGICA DE EXTRAÇÃO ROBUSTA (BRACKET BALANCING) ---
def extrair_json_balanceado(html_content):
    """
    Extrai o objeto JSON da variável VIDEO_CONFIG contando chaves { e }.
    Isso evita erros de Regex quando o JSON do Google contém objetos aninhados.
    """
    marcador = "VIDEO_CONFIG"
    if marcador not in html_content:
        return None
    
    # 1. Encontra onde começa a variável
    inicio_var = html_content.find(marcador)
    
    # 2. Encontra a primeira chave de abertura '{'
    inicio_json = html_content.find('{', inicio_var)
    if inicio_json == -1:
        return None
        
    contador = 0
    fim_json = -1
    encontrou_inicio = False
    
    # 3. Percorre char por char para achar o fechamento correspondente
    for i, char in enumerate(html_content[inicio_json:], start=inicio_json):
        if char == '{':
            contador += 1
            encontrou_inicio = True
        elif char == '}':
            contador -= 1
        
        # Se abriu e fechou tudo (contador voltou a zero), achamos o fim exato
        if encontrou_inicio and contador == 0:
            fim_json = i + 1
            break
            
    if fim_json != -1:
        return html_content[inicio_json:fim_json]
    
    return None

def resolver_link(url, user_agent=None):
    """
    Recebe a URL do Blogger/MP4 e retorna a URL bruta do vídeo.
    """
    # Se já for arquivo de vídeo direto, não faz nada
    if url.endswith('.mp4') or '.mp4?' in url:
        return url

    # Se for link do Blogger
    if 'blogger.com/video.g' in url:
        try:
            # Headers idênticos aos que funcionaram no teste python
            headers = {
                'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.blogger.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            xbmc.log(f"[MeusAnimes] Baixando HTML do Blogger: {url}", xbmc.LOGINFO)
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                xbmc.log(f"[MeusAnimes] Erro HTTP: {response.status_code}", xbmc.LOGERROR)
                return None

            html = response.text
            
            # Usa a nova função de extração balanceada
            json_str = extrair_json_balanceado(html)
            
            if json_str:
                xbmc.log("[MeusAnimes] JSON VIDEO_CONFIG extraído com sucesso.", xbmc.LOGINFO)
                try:
                    data = json.loads(json_str)
                    
                    if 'streams' in data and data['streams']:
                        # Pega o último stream (geralmente a melhor qualidade)
                        play_url = data['streams'][-1]['play_url']
                        xbmc.log(f"[MeusAnimes] Stream encontrado: {play_url[:50]}...", xbmc.LOGINFO)
                        return play_url
                    else:
                        xbmc.log("[MeusAnimes] JSON válido, mas lista 'streams' vazia.", xbmc.LOGWARNING)
                except Exception as e:
                    xbmc.log(f"[MeusAnimes] Erro ao decodificar JSON: {e}", xbmc.LOGERROR)
            else:
                xbmc.log("[MeusAnimes] Falha: VIDEO_CONFIG não encontrado ou extração falhou.", xbmc.LOGERROR)

        except Exception as e:
            xbmc.log(f"[MeusAnimes] Erro fatal no resolver: {e}", xbmc.LOGERROR)
            return None
            
    return url