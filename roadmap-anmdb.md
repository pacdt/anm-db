# Roadmap de Refatoração — `pacdt/anm-db`

> **Escopo:** JSON → SQLite · CDN IPTV · Jikan · Aniskip · Cronjobs diários
> **Estimativa total:** 13–21 dias úteis · 7 fases · 28 tarefas

---

## Visão Geral das Fases

| Fase | Título | Estimativa | Refs |
|------|--------|-----------|------|
| P0 | Análise & Setup | 1–2 dias | — |
| P1 | Migração para Banco de Dados | 3–5 dias | RF01, RNF01 |
| P2 | Integração CDN IPTV (Fonte Primária) | 2–3 dias | RF04, RF05, RN01–RN04, RNF02–RNF03 |
| P3 | Integração Jikan (Catálogo Ongoing) | 2–3 dias | RF02, RNF01, RNF03 |
| P4 | Cronjobs Diários (Ongoing) | 2–3 dias | RF02, RNF01, RNF03 |
| P5 | Integração Aniskip (Skip Times) | 1–2 dias | RF03, RF01 |
| P6 | Otimização & Qualidade | 2–3 dias | RNF01–RNF03 |

---

## Arquitetura Final — Fluxo de Dados

```
APScheduler (scheduler.py)
  ├── 06:00 UTC → jikan_sync         ─────────────────────────┐
  └── 07:00 UTC → scan_ongoing_episodes                        │
                        │                                      ▼
Animefire scraper ──► slug extraction ──────────────► anm.db (SQLite)
                                                              │
                                         ┌────────────────────┤
                                         ▼                    ▼
                                   CDN IPTV #1          CDN IPTV #2    ← asyncio.gather()
                              (mywallpaper-4k...)    (pixel-sus-4k...)
                                         └──────────┬─────────┘
                                                    │ se ambos falharem
                                                    ▼
                                             Animefire API
                                              (fallback)
                                                    │
                                                    ▼
                                         anm.db → episodios
                                                    │
                                         Aniskip API ──► skip_times
                                                    │
                                                    ▼
                                          api.py (queries paginadas)
                                                    │
                                          jsDelivr CDN (static export)
```

---

## Schema do Banco de Dados

```sql
CREATE TABLE animes (
  id            INTEGER PRIMARY KEY,
  mal_id        INTEGER UNIQUE,
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
  next_check_at TEXT,                  -- NULL = não varre (finalizado)
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
  url_cdn     TEXT,                    -- fonte primária (CDN IPTV)
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
  job_id         TEXT NOT NULL,        -- 'jikan_sync' | 'episode_scan'
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  status         TEXT,                 -- 'running' | 'success' | 'error'
  animes_checked INTEGER DEFAULT 0,
  eps_novos      INTEGER DEFAULT 0,
  cdn_hits       INTEGER DEFAULT 0,
  af_fallbacks   INTEGER DEFAULT 0,
  erro_msg       TEXT
);

-- Índices
CREATE INDEX idx_episodios_anime ON episodios(anime_id);
CREATE INDEX idx_animes_status   ON animes(status);
CREATE INDEX idx_animes_updated  ON animes(updated_at DESC);
CREATE INDEX idx_animes_check    ON animes(next_check_at) WHERE next_check_at IS NOT NULL;
```

---

## P0 — Análise & Setup `1–2 dias`

Preparação do ambiente antes de qualquer mudança estrutural no código.

### T0.1 — Auditoria do estado atual

Mapear todos os pontos do `script.py` que leem/escrevem JSON. As funções críticas a identificar são `save_json_async`, `load_json_async`, `carregar_animes_existentes` e `atualizar_anime`. Documentar o schema implícito dos JSONs existentes para garantir que nenhum campo seja perdido na migração.

### T0.2 — Escolha do banco de dados `RF01 · RNF01`

**Recomendação:** SQLite via `aiosqlite` — zero dependência externa, nativo no Python, suporte a WAL mode para leituras concorrentes sem bloqueio de escrita.

**Alternativa:** PostgreSQL, se escala horizontal for prioridade futura. Definir se o arquivo `.db` ficará no repo (`.gitignore`) ou em volume externo (produção).

### T0.3 — Criar branch de refatoração

```
git checkout -b refactor/database-migration
```

Adicionar `anm.db` ao `.gitignore`. Manter `main` funcional com o sistema JSON durante toda a transição — nenhum merge antes da Fase 1 estar completa e testada.

### T0.4 — Instalar dependências novas `RF02 · RF03`

```
pip install aiosqlite apscheduler>=4.0 aiohttp
```

Atualizar `requirements.txt`. Verificar compatibilidade com Python 3.11+. O `APScheduler 4.x` possui API async nativa e será usado na Fase 4.

---

## P1 — Migração para Banco de Dados `3–5 dias`

Substituição completa do sistema de pastas JSON pelo SQLite. Maior bloco da refatoração.

### T1.1 — Definir schema do banco `RF01`

Implementar o schema completo conforme definido na seção acima. Ativar WAL mode e `PRAGMA busy_timeout = 5000` para lidar com concorrência de leitura/escrita do scraper.

### T1.2 — Criar módulo `db.py` `RF01 · RNF01`

Classe `DatabaseManager` com os seguintes métodos:

| Método | Descrição |
|--------|-----------|
| `init_db()` | Cria tabelas e índices se não existirem |
| `upsert_anime(data)` | INSERT OR REPLACE na tabela `animes` |
| `upsert_episodio(anime_id, numero, url_cdn, url_af)` | INSERT OR REPLACE na tabela `episodios` |
| `get_anime_by_slug(slug)` | Retorna metadados do anime |
| `get_ongoing_due()` | Animes com `next_check_at <= now()` |
| `list_all_slugs()` | Retorna todos os slugs cadastrados |
| `reschedule_next_check(anime_ids, hours)` | Atualiza `next_check_at` para `now() + hours` |
| `get_episodios_paginados(slug, page, limit)` | Retorna episódios sem carregar tudo em memória |

> **Regra crítica (RNF01):** nunca carregar todos os episódios de um anime em memória. Sempre usar cursores paginados ou `fetchmany()`.

### T1.3 — Script de migração one-shot `RF01`

Criar `migrate.py` que:

1. Itera sobre todos os JSONs em `Episodios/Dublados/` e `Episodios/Legendados/`
2. Insere cada anime e seus episódios no banco via `db.upsert_anime()` + `db.upsert_episodio()`
3. Valida contagem final (total JSONs = total rows no banco)
4. Loga qualquer divergência

Executar apenas **uma vez**. Manter os JSONs como backup por 30 dias antes de remover do repo.

### T1.4 — Refatorar `script.py` — camada de I/O `RF01 · RNF01`

| Remover | Substituir por |
|---------|---------------|
| `save_json_async(path, data)` | `db.upsert_episodio(...)` |
| `load_json_async(path)` | `db.get_anime_by_slug(slug)` |
| `carregar_animes_existentes(pasta)` | `db.list_all_slugs()` |
| Variáveis `FOLDER_DUBLADOS`, `FOLDER_LEGENDADOS` | _(remover)_ |
| `os.listdir()` + leitura de pasta | _(remover)_ |

O método `atualizar_anime()` passa a escrever diretamente no banco ao confirmar um episódio.

### T1.5 — Refatorar `api.py` `RF01 · RNF01`

Substituir leitura de `all.json`, `one-piece.json` etc. por queries ao banco. Implementar paginação nos endpoints de listagem:

```
GET /animes?page=1&limit=30
GET /animes/{slug}
GET /genres/{slug}
```

Manter compatibilidade de resposta JSON com a API atual para não quebrar clientes existentes.

---

## P2 — Integração CDN IPTV `2–3 dias`

Motor de descoberta de episódios via CDN paralelo, promovendo o CDN como fonte primária e rebaixando o Animefire a fallback.

### T2.1 — Criar módulo `cdn_checker.py` `RF04 · RN01 · RN02 · RN03`

```python
CDN_DOMAINS = [
    "cdn-s01.mywallpaper-4k-image.net",
    "pixel-sus-4k-image.com",
]

def format_ep(numero: int) -> str:
    return str(numero).zfill(2)  # RN03: zero-padding

def build_url(domain: str, slug: str, ep: int) -> str:
    # RN01: formato canônico de URL
    return f"https://{domain}/stream/{slug[0]}/{slug}/{format_ep(ep)}.mp4/index.m3u8"

async def check_cdn_episode(slug: str, numero: int) -> str | None:
    urls = [build_url(d, slug, numero) for d in CDN_DOMAINS]
    tasks = [head_request(u) for u in urls]
    # RNF02: ambos os domínios em paralelo
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for url, result in zip(urls, results):
        if result == 200:
            return url
    return None  # nenhum domínio respondeu → acionar fallback
```

### T2.2 — Concorrência e tolerância a falhas `RF04 · RNF02 · RNF03`

- `asyncio.gather(return_exceptions=True)` — falha em um CDN não cancela o outro
- Timeout individual de **8s** por requisição de HEAD
- Se ambos retornarem erro/timeout → `return None` silenciosamente e acionar fallback
- Nenhuma exceção deve propagar para fora de `check_cdn_episode()`

### T2.3 — Validar pré-condição de slug `RN04`

Antes de qualquer chamada ao CDN, verificar:

```python
anime = await db.get_anime_by_slug(slug)
if not anime:
    logger.warning(f"Slug '{slug}' não encontrado no banco. Pulando CDN.")
    return
```

Nunca consultar o CDN para um slug que não existe no banco.

### T2.4 — Integrar no fluxo principal `RF05`

Lógica de `atualizar_anime()` após a refatoração:

```
1. check_cdn_episode(slug, ep_numero)
   ├── URL encontrada → upsert(url_cdn=url, fonte_ativa='cdn')
   └── None → obter_link_video(slug, ep_numero)  [Animefire]
               ├── URL encontrada → upsert(url_af=url, fonte_ativa='animefire')
               └── None → episódio não disponível ainda, pular
```

---

## P3 — Integração Jikan `2–3 dias`

Sincroniza metadados dos animes em andamento e marca quais slugs devem ser varridos pelo cronjob diário.

### T3.1 — Criar módulo `jikan.py` `RF02 · RNF03`

```
GET https://api.jikan.moe/v4/anime?status=airing&order_by=score&sort=desc&page={n}
```

Campos a parsear: `mal_id`, `title`, `title_english`, `images`, `score`, `synopsis`, `genres`, `status`.

- Paginação: iterar até `last_visible_page`
- Rate limit Jikan: **3 req/s** → `asyncio.Semaphore(3)`
- Em caso de `429` ou `503`: esperar 60s e tentar novamente (máx 3x)
- Timeout por request: 10s

### T3.2 — Rotina de sincronização de metadados `RF02`

`sync_jikan_catalog()` busca todos os animes `airing` do Jikan e executa `upsert_anime()` para cada um, atualizando apenas os campos de metadados: `score`, `sinopse`, `status`, `trailer_url`, `mal_id`. **Nunca sobrescreve episódios.**

### T3.3 — Adicionar coluna `next_check_at` `RF02 · RNF01`

```sql
ALTER TABLE animes ADD COLUMN next_check_at TEXT;
```

**Regras de negócio:**

| Condição | Ação |
|----------|------|
| `status = 'ongoing'` confirmado via Jikan | `next_check_at = datetime('now')` |
| `status = 'finished'` confirmado via Jikan | `next_check_at = NULL` |
| Anime não encontrado no Jikan | manter valor anterior |

O scheduler (Fase 4) usa essa coluna como fila — só varre animes onde `next_check_at <= now()`. Animes finalizados ficam fora da query para sempre.

---

## P4 — Cronjobs Diários `2–3 dias`

Sistema de agendamento autônomo que varre diariamente os episódios novos apenas dos animes com `status = 'ongoing'`.

### T4.1 — Criar módulo `scheduler.py` com APScheduler `RF02 · RNF01`

```python
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

async def main():
    async with AsyncScheduler() as scheduler:
        # Job 1 — 06:00 UTC: atualiza metadados via Jikan
        await scheduler.add_schedule(
            sync_jikan_catalog,
            CronTrigger(hour=6, minute=0),
            id="jikan_sync"
        )
        # Job 2 — 07:00 UTC: varre episódios dos ongoing
        await scheduler.add_schedule(
            scan_ongoing_episodes,
            CronTrigger(hour=7, minute=0),
            id="episode_scan"
        )
        await scheduler.run_until_stopped()
```

> O intervalo de 1h entre os jobs garante que os metadados Jikan (incluindo `next_check_at`) estejam atualizados antes da varredura de episódios começar.

### T4.2 — Implementar `scan_ongoing_episodes()` `RF02 · RF04 · RF05 · RNF01`

```python
async def scan_ongoing_episodes():
    # 1. Busca apenas animes com next_check_at <= now() — query indexada
    animes = await db.get_ongoing_due()

    # 2. Para cada anime: CDN → fallback Animefire (lógica da Fase 2)
    tasks = [atualizar_anime(a) for a in animes]
    await asyncio.gather(*tasks)

    # 3. Reagenda próxima verificação para 24h à frente
    await db.reschedule_next_check([a["id"] for a in animes], hours=24)
```

### T4.3 — Tabela `job_runs` — histórico e auditoria `RNF01`

Registrar início e fim de cada execução na tabela `job_runs` (schema na seção de banco de dados acima). Permite:

- Verificar se o cronjob rodou hoje
- Monitorar quantos episódios novos foram encontrados por execução
- Diagnosticar falhas com `erro_msg`
- Comparar CDN hits vs. Animefire fallbacks ao longo do tempo

### T4.4 — Estratégia de deploy do scheduler `RNF03`

Três opções, em ordem de recomendação conforme o ambiente:

**Opção A — GitHub Actions** _(curto prazo, zero infraestrutura)_

```yaml
on:
  schedule:
    - cron: '0 6 * * *'   # Jikan sync — 06:00 UTC
    - cron: '0 7 * * *'   # Episode scan — 07:00 UTC

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: python main.py --mode=jikan-sync   # ou --mode=ongoing
```

**Opção B — Processo daemon com systemd** _(servidor dedicado / VPS)_

```ini
[Unit]
Description=anm-db scheduler daemon

[Service]
ExecStart=python /app/scheduler.py
Restart=always
RestartSec=30
WorkingDirectory=/app

[Install]
WantedBy=multi-user.target
```

**Opção C — Cron do sistema operacional** _(simples, sem APScheduler)_

```cron
0 6 * * *  cd /app && python main.py --mode=jikan-sync
0 7 * * *  cd /app && python main.py --mode=ongoing
```

> **Recomendação:** começar com Opção A (GitHub Actions), migrar para Opção B quando houver servidor dedicado.

### T4.5 — Flag `--mode` para execução seletiva `RF02 · RNF01`

```python
# main.py
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["full", "ongoing", "jikan-sync", "migrate"],
                    default="full")
args = parser.parse_args()
```

| Modo | Comportamento |
|------|--------------|
| `full` | Varredura completa: catálogo + episódios (comportamento atual) |
| `ongoing` | Só animes com `next_check_at <= now()` (cronjob diário) |
| `jikan-sync` | Só atualiza metadados Jikan (sem tocar episódios) |
| `migrate` | Executa `migrate.py` one-shot |

---

## P5 — Integração Aniskip `1–2 dias`

Busca automática de timestamps de intro/ending para enriquecer os dados dos episódios.

### T5.1 — Criar módulo `aniskip.py` `RF03`

```
GET https://api.aniskip.com/v2/skip-times/{mal_id}/{ep_numero}?types[]=op&types[]=ed
```

- Requer `mal_id`, disponível após integração Jikan (Fase 3)
- Parsear: `type` (`op` / `ed`), `startTime`, `endTime`
- `404` → episódio sem skip times cadastrados, ignorar silenciosamente
- Não bloquear o fluxo principal do scraper

### T5.2 — Inserir skip times no banco `RF03 · RF01`

Ao confirmar um episódio novo (CDN ou Animefire):

```python
# Dispara em background sem bloquear o loop principal
asyncio.create_task(fetch_and_save_skip_times(mal_id, ep_numero))
```

Persiste na tabela `skip_times` com `INSERT OR REPLACE`.

### T5.3 — Expor na API `RF03`

Adicionar campo `skip_times` ao endpoint `/animes/{slug}.json`:

```json
{
  "skip_times": {
    "op": { "start": 5.2, "end": 89.4 },
    "ed": { "start": 1320.0, "end": 1410.0 }
  }
}
```

Campo `null` ou ausente se não houver dados no Aniskip para aquele episódio.

---

## P6 — Otimização & Qualidade `2–3 dias`

Hardening do sistema, testes e preparação para operação contínua.

### T6.1 — Semaphore para writes no SQLite `RNF01 · RNF02`

O `RateLimiter` atual é por sessão HTTP. Adicionar controle de concorrência no acesso ao banco:

```python
db_write_sem = asyncio.Semaphore(1)  # SQLite não suporta writes simultâneos sem WAL

async def safe_write(coro):
    async with db_write_sem:
        return await coro
```

Configurar: `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000`.

### T6.2 — Testes de integração `RNF03`

Cenários obrigatórios a cobrir:

| Cenário | Comportamento esperado |
|---------|----------------------|
| CDN #1 offline | CDN #2 responde, episódio salvo |
| CDN #1 e #2 offline | Fallback para Animefire |
| Jikan retorna 503 | Log de erro, varredura de episódios continua normalmente |
| Aniskip retorna 429 | Skip time não salvo, nenhum crash |
| Scheduler não inicializa | Systemd reinicia em 30s |
| `scan_ongoing_episodes` com banco vazio | Retorna sem erro |

Stack: `pytest-asyncio` + `aioresponses` para mock de HTTP.

### T6.3 — Logging estruturado `RNF01`

Adicionar métricas ao relatório de execução de cada job:

```
[07:00:01] ⚡ episode_scan iniciado — 142 animes ongoing na fila
[07:04:33] ✅ episode_scan concluído
           Animes verificados : 142
           Episódios novos    : 18
           CDN hits           : 15  (83%)
           AF fallbacks       : 3   (17%)
           Skip times salvos  : 18
           Tempo total        : 4m 32s
```

### T6.4 — Limpeza do repositório

- Remover pasta `Episodios/` (substituída pelo banco)
- Remover `animes_dublados.json` e `animes_legendados.json` da raiz
- Remover `jikan_cache/` (cache migrado para tabela no banco)
- Atualizar `README.md` com o novo fluxo de dados e instruções de setup
- Criar `CONTRIBUTING.md` com:
  - Como rodar `migrate.py`
  - Como inicializar o banco localmente
  - Como executar cada `--mode`
  - Como rodar os testes

---

## Dependências Finais

```
# requirements.txt
aiohttp>=3.9
aiofiles>=23.0
aiosqlite>=0.20
apscheduler>=4.0
beautifulsoup4>=4.12
```

---

---

## ⚠️ Observação Crítica — Persistência do Banco de Dados

O arquivo `anm.db` representa **todo o trabalho acumulado** do scraper (slugs, episódios, skip times, histórico de jobs). Perder esse arquivo por um restart de container ou atualização de código significa ter que re-executar o scraper completo desde o zero — horas de processamento e milhares de requisições desperdiçadas.

### Regra fundamental

> O sistema **nunca deve sobrescrever, recriar ou ignorar** um banco de dados existente. A primeira ação de qualquer inicialização deve ser verificar se `anm.db` já existe e, se sim, continuar de onde parou.

### Implementação em `db.py`

```python
async def init_db(path: str = "anm.db"):
    """
    Inicializa o banco de dados de forma segura.
    - Se o arquivo já existe: conecta e aplica apenas migrações pendentes.
    - Se não existe: cria do zero com o schema completo.
    Nunca apaga dados existentes.
    """
    db_exists = os.path.exists(path)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")

        if db_exists:
            logger.info(f"✅ Banco existente encontrado em '{path}'. Continuando de onde parou.")
            await apply_pending_migrations(db)  # apenas ALTER TABLE se necessário
        else:
            logger.info(f"🆕 Banco não encontrado. Criando schema completo em '{path}'.")
            await create_schema(db)

        await db.commit()
```

### Verificação de retomada no scraper

Ao iniciar `scan_ongoing_episodes()` ou qualquer modo de execução, o sistema deve consultar o banco antes de tomar qualquer decisão:

```python
async def atualizar_anime(anime):
    slug = anime["slug"]

    # Busca o último episódio já salvo para continuar de onde parou
    ultimo_ep = await db.get_ultimo_episodio(slug)  # retorna 0 se nenhum
    proximo_ep = ultimo_ep + 1

    logger.info(f"[{slug}] Último ep salvo: {ultimo_ep}. Iniciando varredura a partir de ep {proximo_ep}.")
    # ... continua a busca a partir de proximo_ep
```

Isso garante que um anime com 800 episódios já salvos **não seja re-varrido do episódio 1** a cada execução.

### Configuração Docker — volume obrigatório

O `anm.db` **nunca deve ficar dentro do container**. Deve ser montado como volume externo para sobreviver a `docker stop`, `docker rm` e `docker pull` de novas versões da imagem:

```yaml
# docker-compose.yml
services:
  anmdb:
    build: .
    volumes:
      - ./data:/app/data        # diretório persistente no host
    environment:
      - DB_PATH=/app/data/anm.db

  # Alternativa com volume nomeado (mais portável):
  # volumes:
  #   - anmdb_data:/app/data
  #
  # volumes:
  #   anmdb_data:
```

```python
# main.py — ler o caminho do banco via variável de ambiente
import os

DB_PATH = os.getenv("DB_PATH", "anm.db")  # fallback para desenvolvimento local
```

### Checklist de segurança por evento

| Evento | O que acontece | Garantia |
|--------|---------------|----------|
| `docker stop` / `docker start` | Container reinicia, volume montado | `anm.db` intacto, scraper continua do último ep |
| `docker pull` + nova imagem | Imagem atualizada, volume mantido | `anm.db` intacto, `init_db()` detecta existente |
| `git pull` + reinício manual | Código atualizado | `apply_pending_migrations()` aplica apenas colunas novas |
| Crash inesperado do processo | WAL mode garante integridade | Nenhuma transação parcial no banco |
| Primeira execução (banco ausente) | `anm.db` não existe | `create_schema()` cria do zero normalmente |

### Migrações de schema (sem perda de dados)

Ao adicionar novas colunas em futuras versões, **nunca recriar tabelas**. Usar `ALTER TABLE`:

```python
MIGRATIONS = [
    # versão 2 — adicionado next_check_at
    "ALTER TABLE animes ADD COLUMN next_check_at TEXT",
    # versão 3 — adicionado score_jikan
    "ALTER TABLE animes ADD COLUMN score_jikan REAL",
]

async def apply_pending_migrations(db):
    current = await get_schema_version(db)
    for i, sql in enumerate(MIGRATIONS[current:], start=current + 1):
        await db.execute(sql)
        await set_schema_version(db, i)
        logger.info(f"Migração {i} aplicada: {sql[:60]}...")
```

---

## Ordem de Execução Recomendada

```
P0 (setup) → P1 (banco) → P2 (CDN) → P3 (Jikan) → P4 (scheduler) → P5 (Aniskip) → P6 (hardening)
                ↑
         Não avançar para P2 antes de migrate.py validado e api.py refatorada.
```

As fases P3 → P4 são fortemente acopladas: o campo `next_check_at` (P3) é o mecanismo que a fila do scheduler (P4) consome. Implementar nessa ordem.

---

*anm-db refactor roadmap · pacdt/anm-db*
