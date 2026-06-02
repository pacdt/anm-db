# anm-db

API de dados de animes em Portugues com scraper automatico, banco de dados SQLite e integracao com CDN IPTV.

## Arquitetura

```
APScheduler (scheduler.py)
  |-- 06:00 UTC -> jikan_sync
  '-- 07:00 UTC -> scan_ongoing_episodes
                        |
Animefire scraper --> slug extraction --> anm.db (SQLite)
                                              |
                           +------------------+
                           |                  |
                     CDN IPTV #1          CDN IPTV #2    <- asyncio.gather()
                (mywallpaper-4k...)    (pixel-sus-4k...)
                           +--------+---------+
                                    | se ambos falharem
                                    v
                             Animefire API (fallback)
                                    |
                                    v
                             anm.db -> episodios
                                    |
                             Aniskip API --> skip_times
                                    |
                                    v
                             FastAPI (api/)
                                    |
                                    v
                             Cliente HTTP
```

## Stack

- **Python 3.11+**
- **SQLite** (aiosqlite) -- banco de dados assincrono
- **FastAPI** -- API REST dinamica com Swagger
- **aiohttp** -- requests HTTP assincronos
- **BeautifulSoup** -- scraping de HTML
- **APScheduler 3.x** -- cronjobs diarios
- **Docker** -- containerizacao

## Inicio Rapido

### Com Docker (Recomendado)

```bash
git clone https://github.com/pacdt/anm-db.git
cd anm-db
docker compose up -d
```

A API estara disponivel em `http://localhost:8000/docs`

### Sem Docker

```bash
git clone https://github.com/pacdt/anm-db.git
cd anm-db
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py --mode=migrate    # Migra dados existentes (se houver)
python main.py --mode=api        # Inicia a API
```

## Modos de Execucao

| Modo | Descricao |
|------|-----------|
| `full` | Varredura completa: catalogo + episodios (comportamento original) |
| `ongoing` | Soca animes com `next_check_at <= now()` (cronjob diario) |
| `jikan-sync` | Atualiza metadados via Jikan API (sem tocar episodios) |
| `migrate` | Migracao one-shot: JSON -> SQLite |
| `api` | Inicia servidor FastAPI na porta 8000 |
| `scheduler` | Inicia APScheduler com cronjobs diarios |

```bash
# Exemplos
python main.py --mode=full
python main.py --mode=ongoing
python main.py --mode=jikan-sync
python main.py --mode=api
python main.py --mode=scheduler
```

## Banco de Dados

### Schema

```sql
CREATE TABLE animes (
    id            INTEGER PRIMARY KEY,
    mal_id        INTEGER,
    slug          TEXT NOT NULL UNIQUE,
    tipo          TEXT NOT NULL,         -- 'dublado' | 'legendado'
    titulo        TEXT,
    titulo_en     TEXT,
    titulo_jp     TEXT,
    imagem        TEXT,
    score         REAL,
    sinopse       TEXT,
    trailer_url   TEXT,
    status        TEXT,                  -- 'ongoing' | 'finished'
    next_check_at TEXT,                  -- NULL = nao varre (finalizado)
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE generos (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE anime_generos (
    anime_id  INTEGER REFERENCES animes(id),
    genero_id INTEGER REFERENCES generos(id),
    PRIMARY KEY (anime_id, genero_id)
);

CREATE TABLE episodios (
    id          INTEGER PRIMARY KEY,
    anime_id    INTEGER NOT NULL REFERENCES animes(id),
    numero      INTEGER NOT NULL,
    titulo      TEXT,
    url_cdn     TEXT,                    -- fonte primaria (CDN IPTV)
    url_af      TEXT,                    -- fonte fallback (Animefire)
    fonte_ativa TEXT DEFAULT 'cdn',      -- 'cdn' | 'animefire'
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE (anime_id, numero)
);

CREATE TABLE skip_times (
    id         INTEGER PRIMARY KEY,
    anime_id   INTEGER NOT NULL REFERENCES animes(id),
    ep_numero  INTEGER NOT NULL,
    tipo       TEXT,                     -- 'op' | 'ed'
    start_time REAL,
    end_time   REAL,
    UNIQUE (anime_id, ep_numero, tipo)
);

CREATE TABLE job_runs (
    id             INTEGER PRIMARY KEY,
    job_id         TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    status         TEXT,
    animes_checked INTEGER DEFAULT 0,
    eps_novos      INTEGER DEFAULT 0,
    cdn_hits       INTEGER DEFAULT 0,
    af_fallbacks   INTEGER DEFAULT 0,
    erro_msg       TEXT
);
```

### Estatisticas

| Metrica | Valor |
|---------|-------|
| Animes | 5.166 |
| Episodios | 78.520 |
| Generos | 21 |
| Dublados | 673 |
| Legendados | 4.493 |

### Persistencia

O arquivo `anm.db` contem todo o trabalho acumulado do scraper. Nunca sobrescrever, recriar ou ignorar um banco existente.

**Regras:**
- Docker: montar volume externo (`./data:/app/data`)
- Nunca colocar `anm.db` no repositorio
- `init_db()` detecta banco existente e continua de onde parou
- Migracoes via `ALTER TABLE` (sem perda de dados)

## API (FastAPI)

### Endpoints

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/` | Info da API |
| GET | `/health` | Health check |
| GET | `/animes` | Lista paginada de animes |
| GET | `/animes/{slug}` | Detalhe do anime com episodios |
| GET | `/genres` | Lista de generos com contagem |
| GET | `/genres/{nome}` | Animes por genero |
| GET | `/episodes/latest` | Ultimos episodios |

### Parametros de Query

**GET /animes:**
- `page` (int, padrao: 1)
- `limit` (int, padrao: 30, max: 100)
- `status` (string, opcional): filtrar por status
- `search` (string, opcional): buscar por titulo ou slug

### Exemplos

```bash
# Listar animes
curl "http://localhost:8000/animes?page=1&limit=10"

# Buscar anime
curl "http://localhost:8000/animes?search=one-piece"

# Detalhe do anime
curl "http://localhost:8000/animes/one-piece"

# Generos
curl "http://localhost:8000/genres"

# Ultimos episodios
curl "http://localhost:8000/episodes/latest?limit=10"
```

### Documentacao Interativa

- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Cronjobs

### Configuracao

**GitHub Actions (curto prazo):**

```yaml
on:
  schedule:
    - cron: '0 6 * * *'   # Jikan sync - 06:00 UTC
    - cron: '0 7 * * *'   # Episode scan - 07:00 UTC

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: python main.py --mode=jikan-sync
```

**Docker Compose (producao):**

```bash
docker compose up -d scheduler
```

### Fluxo Diario

```
06:00 UTC -- jikan_sync (atualiza metadados)
07:00 UTC -- episode_scan (varre episodios novos)
```

### Historico de Execucoes

Tabela `job_runs` registra inicio/fim de cada execucao com metricas:
- Animes verificados
- Episodios novos encontrados
- CDN hits vs Animefire fallbacks
- Erros (se houver)

## Docker

### docker-compose.yml

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - DB_PATH=/app/data/anm.db
    command: python main.py --mode=api
    restart: unless-stopped

  scheduler:
    build: .
    volumes:
      - ./data:/app/data
    environment:
      - DB_PATH=/app/data/anm.db
    command: python main.py --mode=scheduler
    restart: unless-stopped
```

### Variaveis de Ambiente

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `DB_PATH` | Caminho do banco SQLite | `anm.db` |

## Estrutura do Projeto

```
anm-db/
|-- main.py              # Entry point (--mode flag)
|-- db.py                # DatabaseManager (aiosqlite)
|-- script.py            # Scraper (animefire.plus)
|-- cdn_checker.py       # Motor CDN paralelo
|-- jikan.py             # Sync metadados Jikan
|-- aniskip.py           # Skip times
|-- scheduler.py         # APScheduler (cronjobs)
|-- migrate.py           # Migracao one-shot JSON -> SQLite
|-- api/                 # FastAPI application
|   |-- main.py          # FastAPI app + startup/shutdown
|   |-- schemas.py       # Pydantic models
|   |-- deps.py          # Dependency injection
|   +-- routes/          # Endpoints
|       |-- animes.py
|       |-- genres.py
|       +-- episodes.py
|-- tests/               # Testes automatizados
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
+-- pyproject.toml       # Config pytest
```

## Desenvolvimento

### Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Testes

```bash
python -m pytest tests/ -v
```

### Estrutura de Testes

| Arquivo | Cenarios |
|---------|----------|
| `test_db.py` | 14 testes -- CRUD completo do banco |
| `test_cdn.py` | 5 testes -- URL building, fallback, erros |
| `test_jikan.py` | 4 testes -- parsing de dados Jikan |
| `test_scheduler.py` | 3 testes -- scheduler, imports, config |
| `test_aniskip.py` | 2 testes -- API Aniskip, erros |

## Licenca

Projeto privado -- pacdt/anm-db
