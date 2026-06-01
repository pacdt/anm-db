# anm-db API Documentation

> API de dados de animes com scraper automático, integração CDN IPTV, Jikan sync e Aniskip skip times.

**Base URL:** `http://localhost:8000` (local) ou `http://167.234.240.167:3000` (produção via nginx)

**Versão:** 2.0.0

**Swagger UI:** `http://localhost:8000/docs`

---

## Índice

- [Visão Geral](#visão-geral)
- [Autenticação](#autenticação)
- [Formatação de Resposta](#formatação-de-resposta)
- [Erros](#erros)
- [Endpoints](#endpoints)
  - [Root](#root)
  - [Health Check](#health-check)
  - [Animes](#animes)
  - [Genres](#genres)
  - [Episodes](#episodes)
  - [Download](#download)
- [Modelos de Dados](#modelos-de-dados)
- [Exemplos cURL](#exemplos-curl)
- [Fontes de Vídeo](#fontes-de-vídeo)

---

## Visão Geral

A API fornece acesso a dados de animes coletados automaticamente via scraping de sites de streaming. Cada episódio pode possuir até duas fontes de vídeo:

| Fonte | Formato | Domínio |
|-------|---------|---------|
| **CDN** (primária) | HLS (`.m3u8`) | `cdn-s01.mywallpaper-4k-image.net` |
| **AnimeFire** (fallback) | MP4 (via Blogger) | `www.blogger.com` → `bp.blogspot.com` |

---

## Autenticação

A API é **pública**. Não há autenticação ou rate limiting no lado do servidor.

---

## Formatação de Resposta

Todas as respostas são JSON com `Content-Type: application/json`.

### Paginação

Endpoints paginados retornam:

```json
{
  "items": [...],
  "total": 5166,
  "page": 1,
  "limit": 30,
  "pages": 173
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `items` | `array` | Lista de itens da página atual |
| `total` | `int` | Total de itens |
| `page` | `int` | Página atual (1-indexed) |
| `limit` | `int` | Itens por página |
| `pages` | `int` | Total de páginas |

---

## Erros

| HTTP Code | Descrição |
|-----------|-----------|
| `404` | Recurso não encontrado |
| `422` | Parâmetros de validação inválidos |
| `500` | Erro interno do servidor |

Formato do erro:

```json
{
  "detail": "Anime not found"
}
```

---

## Endpoints

### Root

#### `GET /`

Informações básicas da API.

**Response:**

```json
{
  "name": "anm-db API",
  "version": "2.0.0",
  "docs": "/docs"
}
```

---

### Health Check

#### `GET /health`

Verificação de saúde do serviço.

**Response:**

```json
{
  "status": "ok"
}
```

---

### Animes

#### `GET /animes`

Lista todos os animes com paginação e filtros opcionais.

**Parâmetros Query:**

| Nome | Tipo | Obrigatório | Padrão | Descrição |
|------|------|-------------|--------|-----------|
| `page` | `int` | Não | `1` | Página (≥ 1) |
| `limit` | `int` | Não | `30` | Itens por página (1-100) |
| `status` | `string` | Não | — | Filtrar por status: `ongoing`, `finished` |
| `search` | `string` | Não | — | Buscar por título (parcial, case-insensitive) |

**Response:** `PaginatedResponse`

```json
{
  "items": [
    {
      "title": "One Piece",
      "slug": "one-piece",
      "image": "https://cdn.myanimelist.net/images/animes/...",
      "score": 8.7,
      "type": "dublado"
    }
  ],
  "total": 5166,
  "page": 1,
  "limit": 30,
  "pages": 173
}
```

---

#### `GET /animes/{slug}`

Detalhes completos de um anime, incluindo todos os episódios com URLs de vídeo e skip times.

**Parâmetros Path:**

| Nome | Tipo | Descrição |
|------|------|-----------|
| `slug` | `string` | Identificador único do anime |

**Response:** `AnimeDetail`

```json
{
  "id": 1,
  "mal_id": 21,
  "slug": "one-piece",
  "tipo": "dublado",
  "titulo": "One Piece",
  "titulo_en": "One Piece",
  "titulo_jp": "ワンピース",
  "imagem": "https://cdn.myanimelist.net/images/animes/...",
  "score": 8.7,
  "sinopse": "Gol D. Roger era conhecido como o Rei dos Piratas...",
  "trailer_url": "https://www.youtube.com/watch?v=...",
  "status": "ongoing",
  "genres": ["Ação", "Aventura", "Comédia"],
  "episodes": [
    {
      "numero": 1,
      "titulo": "Romance Dawn",
      "url_cdn": "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8",
      "url_af": "https://www.blogger.com/video.g?token=AD6v5d...",
      "fonte_ativa": "cdn",
      "skip_times": {
        "op": {"start": 1.0, "end": 102.0},
        "ed": {"start": 1100.0, "end": 1200.0}
      }
    }
  ]
}
```

**Erros:**

| Code | Descrição |
|------|-----------|
| `404` | Anime não encontrado |

---

### Genres

#### `GET /genres`

Lista todos os gêneros com contagem de animes.

**Response:**

```json
[
  {
    "id": 1,
    "nome": "Ação",
    "count": 1250
  },
  {
    "id": 2,
    "nome": "Aventura",
    "count": 980
  }
]
```

---

#### `GET /genres/{nome}`

Lista animes de um gênero específico com paginação.

**Parâmetros Path:**

| Nome | Tipo | Descrição |
|------|------|-----------|
| `nome` | `string` | Nome do gênero (ex: `Ação`, `Romance`) |

**Parâmetros Query:**

| Nome | Tipo | Padrão | Descrição |
|------|------|--------|-----------|
| `page` | `int` | `1` | Página (≥ 1) |
| `limit` | `int` | `30` | Itens por página (1-100) |

**Response:** `PaginatedResponse` (mesmo formato de `/animes`)

**Erros:**

| Code | Descrição |
|------|-----------|
| `404` | Gênero não encontrado |

---

### Episodes

#### `GET /episodes/latest`

Retorna os episódios mais recentes adicionados ao banco.

**Parâmetros Query:**

| Nome | Tipo | Padrão | Descrição |
|------|------|--------|-----------|
| `limit` | `int` | `50` | Número de episódios (1-200) |

**Response:**

```json
[
  {
    "id": 78520,
    "anime_id": 1,
    "numero": 1122,
    "titulo": "Romance Dawn",
    "url_cdn": "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8",
    "url_af": "https://www.blogger.com/video.g?token=AD6v5d...",
    "fonte_ativa": "cdn",
    "slug": "one-piece",
    "anime_title": "One Piece",
    "anime_image": "https://cdn.myanimelist.net/images/animes/...",
    "tipo": "dublado",
    "skip_times": {}
  }
]
```

---

#### `GET /episodes/{slug}`

Lista episódios de um anime específico com paginação e skip times.

**Parâmetros Path:**

| Nome | Tipo | Descrição |
|------|------|-----------|
| `slug` | `string` | Slug do anime |

**Parâmetros Query:**

| Nome | Tipo | Padrão | Descrição |
|------|------|--------|-----------|
| `page` | `int` | `1` | Página (≥ 1) |
| `limit` | `int` | `50` | Itens por página (1-200) |

**Response:**

```json
{
  "items": [
    {
      "id": 1,
      "anime_id": 1,
      "numero": 1,
      "titulo": "Romance Dawn",
      "url_cdn": "https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8",
      "url_af": "https://www.blogger.com/video.g?token=AD6v5d...",
      "fonte_ativa": "cdn",
      "slug": "one-piece",
      "anime_title": "One Piece",
      "anime_image": "https://cdn.myanimelist.net/images/animes/...",
      "tipo": "dublado",
      "skip_times": {
        "op": {"start": 1.0, "end": 102.0},
        "ed": {"start": 1100.0, "end": 1200.0}
      }
    }
  ],
  "total": 1122,
  "page": 1,
  "limit": 50,
  "pages": 23
}
```

**Erros:**

| Code | Descrição |
|------|-----------|
| `404` | Anime não encontrado |

---

### Download

#### `GET /download/{slug}/{numero}`

Faz download de um episódio. Tenta CDN (HLS) primeiro, fallback para AnimeFire (MP4).

**Parâmetros Path:**

| Nome | Tipo | Descrição |
|------|------|-----------|
| `slug` | `string` | Slug do anime |
| `numero` | `int` | Número do episódio |

**Parâmetros Query:**

| Nome | Tipo | Padrão | Descrição |
|------|------|--------|-----------|
| `source` | `string` | `auto` | Forçar fonte: `cdn`, `af`, ou `auto` (CDN → AF) |

**Response:** Stream binário

| Header | Valor |
|--------|-------|
| `Content-Type` | `application/x-mpegurl` (CDN) ou `video/mp4` (AF) |
| `Content-Disposition` | `attachment; filename="{slug}-ep{numero}.ext"` |
| `Transfer-Encoding` | `chunked` |

**Erros:**

| Code | Descrição |
|------|-----------|
| `404` | Episódio não encontrado |
| `502` | Nenhuma fonte de vídeo disponível |
| `504` | Timeout ao resolver URL do Blogger |

---

## Modelos de Dados

### Tabela: `animes`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `INTEGER` | Primary key |
| `mal_id` | `INTEGER` | ID no MyAnimeList |
| `slug` | `TEXT` | Identificador único (URL-friendly) |
| `tipo` | `TEXT` | `dublado` ou `legendado` |
| `titulo` | `TEXT` | Título em português |
| `titulo_en` | `TEXT` | Título em inglês |
| `titulo_jp` | `TEXT` | Título em japonês |
| `imagem` | `TEXT` | URL da imagem de capa |
| `score` | `REAL` | Nota média (0-10) |
| `sinopse` | `TEXT` | Sinopse do anime |
| `trailer_url` | `TEXT` | URL do trailer (YouTube) |
| `status` | `TEXT` | `ongoing` ou `finished` |
| `next_check_at` | `TEXT` | Próxima verificação (ISO datetime) |
| `created_at` | `TEXT` | Data de criação |
| `updated_at` | `TEXT` | Última atualização |

### Tabela: `episodios`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `INTEGER` | Primary key |
| `anime_id` | `INTEGER` | FK → animes(id) |
| `numero` | `INTEGER` | Número do episódio |
| `titulo` | `TEXT` | Título do episódio |
| `url_cdn` | `TEXT` | URL HLS (CDN) |
| `url_af` | `TEXT` | URL AnimeFire (Blogger) |
| `fonte_ativa` | `TEXT` | Fonte ativa: `cdn` ou `animefire` |
| `created_at` | `TEXT` | Data de criação |

### Tabela: `skip_times`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `INTEGER` | Primary key |
| `anime_id` | `INTEGER` | FK → animes(id) |
| `ep_numero` | `INTEGER` | Número do episódio |
| `tipo` | `TEXT` | `op` (abertura) ou `ed` (encerramento) |
| `start_time` | `REAL` | Tempo inicial (segundos) |
| `end_time` | `REAL` | Tempo final (segundos) |

### Tabela: `generos`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `INTEGER` | Primary key |
| `nome` | `TEXT` | Nome do gênero (único) |

### Tabela: `anime_generos` (junção)

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `anime_id` | `INTEGER` | FK → animes(id) |
| `genero_id` | `INTEGER` | FK → generos(id) |

---

## Exemplos cURL

### Listar animes (paginado)
```bash
curl "http://localhost:8000/animes?page=1&limit=10"
```

### Buscar animes por nome
```bash
curl "http://localhost:8000/animes?search=one+piece"
```

### Filtrar por status (ongoing)
```bash
curl "http://localhost:8000/animes?status=ongoing"
```

### Detalhe do anime
```bash
curl "http://localhost:8000/animes/one-piece"
```

### Listar gêneros
```bash
curl "http://localhost:8000/genres"
```

### Animes por gênero
```bash
curl "http://localhost:8000/genres/A%C3%A7%C3%A3o"
```

### Episódios mais recentes
```bash
curl "http://localhost:8000/episodes/latest?limit=10"
```

### Episódios de um anime
```bash
curl "http://localhost:8000/episodes/one-piece?page=1&limit=20"
```

### Download de episódio (auto CDN→AF)
```bash
curl -L -o one-piece-ep1.mp4 "http://localhost:8000/download/one-piece/1"
```

### Download forçando AF
```bash
curl -L -o one-piece-ep1.mp4 "http://localhost:8000/download/one-piece/1?source=af"
```

### Health check
```bash
curl "http://localhost:8000/health"
```

---

## Fontes de Vídeo

### CDN (Primária)

Formato URL:
```
https://cdn-s01.mywallpaper-4k-image.net/stream/{primeira_letra_slug}/{slug}/{episodio_zfill2}.mp4/index.m3u8
```

Exemplo:
```
https://cdn-s01.mywallpaper-4k-image.net/stream/o/one-piece/01.mp4/index.m3u8
```

- Formato: **HLS** (HTTP Live Streaming)
- Extensão: `.m3u8` (manifesto)
- Episódios: zero-padded (01, 02, ..., 99, 100)

### AnimeFire (Fallback)

Formato original:
```
https://www.blogger.com/video.g?token=AD6v5d...
```

Após resolução:
```
https://...bp.blogspot.com/.../video.mp4
```

- Formato: **MP4** direto
- Requer resolução do token Blogger

### Skip Times (Aniskip)

Fonte: API pública [Aniskip](https://aniskip.com)

Cada episódio pode ter:
- **OP** (Opening): tempo de início e fim da abertura
- **ED** (Ending): tempo de início e fim do encerramento

Útil para:
- Pular aberturas/encerramentos em players
- Mostrar timestamps em interfaces

---

## Arquitetura

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Scraper   │────▶│   SQLite    │◀────│    API      │
│  (CDN + AF) │     │   (WAL)     │     │  (FastAPI)  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │              ┌────┴────┐              │
       │              │  nginx  │◀─────────────┘
       │              │ (proxy) │
       │              └─────────┘
       │
┌──────┴──────┐
│  Scheduler  │
│ (APScheduler│
│  3 cronjobs)│
└─────────────┘

Cronjobs:
  06:00 → jikan_sync (metadados)
  07:00 → episode_scan (episódios novos)
  08:00 → backfill_skip_times
```

---

## Deploy

### Docker Compose

```bash
# Deploy completo
git pull --rebase origin refactor/database-migration
bash deploy.sh

# Verificar status
docker compose ps

# Ver logs
docker compose logs -f api
```

### Serviços

| Serviço | Porta | Descrição |
|---------|-------|-----------|
| `api` | `8000` | FastAPI (via entrypoint.sh) |
| `scheduler` | — | APScheduler (cronjobs) |
| `nginx` | `3000` | Reverse proxy |

### Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DB_PATH` | `anm.db` | Caminho do banco SQLite |

### Volumes

| Host | Container | Descrição |
|------|-----------|-----------|
| `./data` | `/app/data` | Banco SQLite persistido |
