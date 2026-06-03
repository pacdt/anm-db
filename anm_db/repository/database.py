"""
DatabaseManager - camada de acesso a dados SQLite via aiosqlite.

Schema evoluido com:
  - Tabela jikan_metadata (clone normalizado do payload Jikan)
  - Colunas de traducao PT-BR (titulo_pt, sinopse_pt, titulo_pt nos eps)
  - Tabela translation_log (auditoria de chamadas Gemini)
  - Coluna nome_pt em generos (mapa estatico PT-BR)
  - Indices otimizados para queries quentes
"""

from __future__ import annotations

import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

from anm_db.config import get_settings

logger = logging.getLogger("DB")

# Versao do schema. Bump + adicionar MIGRATIONS quando mudar.
SCHEMA_VERSION = 3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS animes (
    id                       INTEGER PRIMARY KEY,
    mal_id                   INTEGER UNIQUE,
    slug                     TEXT NOT NULL UNIQUE,
    tipo                     TEXT NOT NULL,
    titulo                   TEXT,
    titulo_en                TEXT,
    titulo_jp                TEXT,
    titulo_pt                TEXT,
    imagem                   TEXT,
    score                    REAL,
    sinopse                  TEXT,
    sinopse_pt               TEXT,
    trailer_url              TEXT,
    status                   TEXT,
    next_check_at            TEXT,
    created_at               TEXT DEFAULT (datetime('now')),
    updated_at               TEXT DEFAULT (datetime('now')),
    traduzido_em             TEXT,
    traducao_modelo          TEXT,
    traducao_input_tokens    INTEGER,
    traducao_output_tokens   INTEGER
);

CREATE TABLE IF NOT EXISTS generos (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL UNIQUE,
    nome_pt TEXT
);

CREATE TABLE IF NOT EXISTS anime_generos (
    anime_id  INTEGER REFERENCES animes(id),
    genero_id INTEGER REFERENCES generos(id),
    PRIMARY KEY (anime_id, genero_id)
);

CREATE TABLE IF NOT EXISTS episodios (
    id          INTEGER PRIMARY KEY,
    anime_id    INTEGER NOT NULL REFERENCES animes(id),
    numero      INTEGER NOT NULL,
    titulo      TEXT,
    titulo_pt   TEXT,
    url_cdn     TEXT,
    url_cdn2    TEXT,
    url_af      TEXT,
    fonte_ativa TEXT DEFAULT 'cdn',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE (anime_id, numero)
);

CREATE TABLE IF NOT EXISTS skip_times (
    id         INTEGER PRIMARY KEY,
    anime_id   INTEGER NOT NULL REFERENCES animes(id),
    ep_numero  INTEGER NOT NULL,
    tipo       TEXT,
    start_time REAL,
    end_time   REAL,
    UNIQUE (anime_id, ep_numero, tipo)
);

CREATE TABLE IF NOT EXISTS job_runs (
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

CREATE TABLE IF NOT EXISTS jikan_metadata (
    anime_id            INTEGER PRIMARY KEY REFERENCES animes(id),
    mal_id              INTEGER UNIQUE NOT NULL,
    url                 TEXT,
    approved            INTEGER,
    title_japanese      TEXT,
    title_romaji        TEXT,
    type                TEXT,
    source              TEXT,
    episodes_total      INTEGER,
    episodes_aired      INTEGER,
    status_jikan        TEXT,
    airing              INTEGER,
    aired_from          TEXT,
    aired_to            TEXT,
    duration            TEXT,
    rating              TEXT,
    season              TEXT,
    year                INTEGER,
    broadcast_day       TEXT,
    broadcast_time      TEXT,
    studios_json        TEXT,
    producers_json      TEXT,
    licensors_json      TEXT,
    demographics_json   TEXT,
    themes_json         TEXT,
    relations_json      TEXT,
    external_links_json TEXT,
    streaming_json      TEXT,
    jikan_fetched_at    TEXT NOT NULL,
    jikan_updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translation_log (
    id              INTEGER PRIMARY KEY,
    anime_id        INTEGER NOT NULL REFERENCES animes(id),
    provider        TEXT NOT NULL,
    status          TEXT NOT NULL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    erro_msg        TEXT
);

CREATE INDEX IF NOT EXISTS idx_episodios_anime ON episodios(anime_id);
CREATE INDEX IF NOT EXISTS idx_animes_status   ON animes(status);
CREATE INDEX IF NOT EXISTS idx_animes_updated  ON animes(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_animes_check    ON animes(next_check_at) WHERE next_check_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_animes_mal_id   ON animes(mal_id);
CREATE INDEX IF NOT EXISTS idx_animes_traduzido_em ON animes(traduzido_em);
CREATE INDEX IF NOT EXISTS idx_generos_nome_pt ON generos(nome_pt);
CREATE INDEX IF NOT EXISTS idx_jikan_year      ON jikan_metadata(year);
CREATE INDEX IF NOT EXISTS idx_jikan_status    ON jikan_metadata(status_jikan);
CREATE INDEX IF NOT EXISTS idx_translation_log ON translation_log(anime_id);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""

# Migracoes incrementais: cada chave e a versao de DESTINO, valor e lista de SQLs.
# Para migrar de v1 -> v2, executamos MIGRATIONS[2] na ordem.
# IMPORTANTE: nunca quebrar versoes anteriores. Sempre adicionar nova chave.
MIGRATIONS: dict[int, list[str]] = {
    # v2: traducao PT-BR + jikan_metadata + translation_log + nome_pt em generos
    2: [
        "ALTER TABLE animes ADD COLUMN titulo_pt TEXT",
        "ALTER TABLE animes ADD COLUMN sinopse_pt TEXT",
        "ALTER TABLE animes ADD COLUMN traduzido_em TEXT",
        "ALTER TABLE animes ADD COLUMN traducao_modelo TEXT",
        "ALTER TABLE animes ADD COLUMN traducao_input_tokens INTEGER",
        "ALTER TABLE animes ADD COLUMN traducao_output_tokens INTEGER",
        "ALTER TABLE episodios ADD COLUMN titulo_pt TEXT",
        "ALTER TABLE generos ADD COLUMN nome_pt TEXT",
        "CREATE INDEX IF NOT EXISTS idx_animes_traduzido_em ON animes(traduzido_em)",
        "CREATE TABLE IF NOT EXISTS jikan_metadata ("
        "  anime_id INTEGER PRIMARY KEY REFERENCES animes(id),"
        "  mal_id INTEGER UNIQUE NOT NULL,"
        "  jikan_fetched_at TEXT NOT NULL,"
        "  jikan_updated_at TEXT NOT NULL"
        ")",
        "CREATE TABLE IF NOT EXISTS translation_log ("
        "  id INTEGER PRIMARY KEY,"
        "  anime_id INTEGER NOT NULL REFERENCES animes(id),"
        "  provider TEXT NOT NULL,"
        "  status TEXT NOT NULL,"
        "  started_at TEXT NOT NULL"
        ")",
    ],
    # v3: suporte a 2 fontes CDN (cdn-s01 + pixel-sus) por episodio
    3: [
        "ALTER TABLE episodios ADD COLUMN url_cdn2 TEXT",
    ],
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or get_settings().db_path
        self._db: aiosqlite.Connection | None = None
        self._write_sem = asyncio.Semaphore(1)

    async def connect(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        # Pragmas otimizados para free tier (1GB RAM): WAL + cache + mmap
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA temp_store=MEMORY")
        await self._db.execute("PRAGMA cache_size=-32000")  # 32MB

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def init_db(self):
        """Inicializa o banco de forma segura.
        - Se o arquivo ja existe: conecta e aplica apenas migracoes pendentes.
        - Se nao existe: cria do zero com o schema completo.
        Nunca apaga dados existentes.
        """
        db_exists = os.path.exists(self.db_path) and os.path.getsize(self.db_path) > 0

        await self.connect()

        if db_exists:
            logger.info(f"Banco existente encontrado em '{self.db_path}'. Continuando de onde parou.")
            await self._apply_pending_migrations()
        else:
            logger.info(f"Banco nao encontrado. Criando schema completo em '{self.db_path}'.")
            await self._create_schema()

        await self._db.commit()

    async def _create_schema(self):
        await self._db.executescript(SCHEMA_SQL)
        await self._db.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )

    async def _get_schema_version(self) -> int:
        async with self._db.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    async def _apply_pending_migrations(self):
        try:
            current = await self._get_schema_version()
        except Exception:
            current = 0
            await self._db.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
            )
            await self._db.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (0)"
            )
        # Aplica migracoes de cada versao, na ordem
        for target_version in sorted(MIGRATIONS.keys()):
            if target_version <= current:
                continue
            for sql in MIGRATIONS[target_version]:
                try:
                    await self._db.execute(sql)
                    logger.info(
                        f"Migracao para v{target_version}: {sql[:60]}..."
                    )
                except Exception as e:
                    # Coluna/indice ja existe (migracao parcialmente aplicada)
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        logger.debug(
                            f"Migracao v{target_version} ja aplicada: {sql[:60]}..."
                        )
                    else:
                        raise
            await self._db.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (target_version,),
            )
            logger.info(f"Schema atualizado para v{target_version}")

    async def upsert_anime(self, data: dict) -> int:
        now = _utcnow()
        async with self._write_sem:
            await self._db.execute(
                """
                INSERT INTO animes (mal_id, slug, tipo, titulo, titulo_en, titulo_jp, imagem, score, sinopse, trailer_url, status, updated_at)
                VALUES (:mal_id, :slug, :tipo, :titulo, :titulo_en, :titulo_jp, :imagem, :score, :sinopse, :trailer_url, :status, :updated_at)
                ON CONFLICT(slug) DO UPDATE SET
                    mal_id = excluded.mal_id,
                    titulo = excluded.titulo,
                    titulo_en = excluded.titulo_en,
                    titulo_jp = excluded.titulo_jp,
                    imagem = COALESCE(excluded.imagem, animes.imagem),
                    score = excluded.score,
                    sinopse = excluded.sinopse,
                    trailer_url = excluded.trailer_url,
                    status = excluded.status,
                    updated_at = excluded.updated_at
            """,
                {
                    "mal_id": data.get("mal_id"),
                    "slug": data["slug"],
                    "tipo": data["tipo"],
                    "titulo": data.get("titulo"),
                    "titulo_en": data.get("titulo_en"),
                    "titulo_jp": data.get("titulo_jp"),
                    "imagem": data.get("imagem"),
                    "score": data.get("score"),
                    "sinopse": data.get("sinopse"),
                    "trailer_url": data.get("trailer_url"),
                    "status": data.get("status"),
                    "updated_at": now,
                },
            )
            await self._db.commit()

            async with self._db.execute(
                "SELECT id FROM animes WHERE slug = ?", (data["slug"],)
            ) as cur:
                row = await cur.fetchone()
                return row[0]

    async def upsert_genero(self, nome: str, nome_pt: str | None = None) -> int:
        async with self._write_sem:
            await self._db.execute(
                """
                INSERT INTO generos (nome, nome_pt) VALUES (?, ?)
                ON CONFLICT(nome) DO UPDATE SET nome_pt = COALESCE(excluded.nome_pt, generos.nome_pt)
            """,
                (nome, nome_pt),
            )
            await self._db.commit()
            async with self._db.execute(
                "SELECT id FROM generos WHERE nome = ?", (nome,)
            ) as cur:
                row = await cur.fetchone()
                return row[0]

    async def link_anime_genero(self, anime_id: int, genero_id: int):
        async with self._write_sem:
            await self._db.execute(
                "INSERT OR IGNORE INTO anime_generos (anime_id, genero_id) VALUES (?, ?)",
                (anime_id, genero_id),
            )

    async def upsert_episodio(
        self,
        anime_id: int,
        numero: int,
        titulo: str = None,
        url_cdn: str = None,
        url_cdn2: str = None,
        url_af: str = None,
        fonte_ativa: str = "cdn",
    ):
        async with self._write_sem:
            await self._db.execute(
                """
                INSERT INTO episodios (anime_id, numero, titulo, url_cdn, url_cdn2, url_af, fonte_ativa)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(anime_id, numero) DO UPDATE SET
                    titulo = COALESCE(excluded.titulo, episodios.titulo),
                    url_cdn = COALESCE(excluded.url_cdn, episodios.url_cdn),
                    url_cdn2 = COALESCE(excluded.url_cdn2, episodios.url_cdn2),
                    url_af = COALESCE(excluded.url_af, episodios.url_af),
                    fonte_ativa = excluded.fonte_ativa
            """,
                (anime_id, numero, titulo, url_cdn, url_cdn2, url_af, fonte_ativa),
            )
            await self._db.commit()

    async def get_anime_by_slug(self, slug: str) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM animes WHERE slug = ?", (slug,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_anime_by_id(self, anime_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM animes WHERE id = ?", (anime_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_anime_by_mal_id(self, mal_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM animes WHERE mal_id = ?", (mal_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_ongoing_due(self) -> list[dict]:
        now = _utcnow()
        async with self._db.execute(
            "SELECT * FROM animes WHERE next_check_at IS NOT NULL AND next_check_at <= ?",
            (now,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def list_all_slugs(self) -> list[str]:
        async with self._db.execute("SELECT slug FROM animes") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def reschedule_next_check(self, anime_ids: list[int], hours: int = 24):
        next_time = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        placeholders = ",".join("?" * len(anime_ids))
        async with self._write_sem:
            await self._db.execute(
                f"UPDATE animes SET next_check_at = ? WHERE id IN ({placeholders})",
                [next_time] + anime_ids,
            )
            await self._db.commit()

    async def get_episodios_paginados(
        self, slug: str, page: int = 1, limit: int = 50
    ) -> list[dict]:
        offset = (page - 1) * limit
        async with self._db.execute(
            """
            SELECT e.* FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            WHERE a.slug = ?
            ORDER BY e.numero ASC
            LIMIT ? OFFSET ?
        """,
            (slug, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_ultimo_episodio(self, slug: str) -> int:
        async with self._db.execute(
            """
            SELECT MAX(e.numero) FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            WHERE a.slug = ?
        """,
            (slug,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] else 0

    async def get_episodios_count(self, slug: str) -> int:
        async with self._db.execute(
            """
            SELECT COUNT(*) FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            WHERE a.slug = ?
        """,
            (slug,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    async def get_generos_by_slug(self, slug: str) -> list[dict]:
        """Retorna generos com nome original (EN) e nome_pt."""
        async with self._db.execute(
            """
            SELECT g.nome, COALESCE(g.nome_pt, g.nome) as nome_pt
            FROM generos g
            JOIN anime_generos ag ON g.id = ag.genero_id
            JOIN animes a ON ag.anime_id = a.id
            WHERE a.slug = ?
        """,
            (slug,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def list_animes_paginado(
        self,
        page: int = 1,
        limit: int = 30,
        status: str = None,
        search: str = None,
    ) -> list[dict]:
        conditions = []
        params = []
        if status:
            conditions.append("a.status = ?")
            params.append(status)
        if search:
            conditions.append(
                "(a.titulo LIKE ? OR a.titulo_en LIKE ? OR a.titulo_pt LIKE ? OR a.slug LIKE ?)"
            )
            params.extend([f"%{search}%"] * 4)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * limit

        async with self._db.execute(
            f"""
            SELECT a.* FROM animes a
            {where}
            ORDER BY a.updated_at DESC
            LIMIT ? OFFSET ?
        """,
            params + [limit, offset],
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def count_animes(self, status: str = None) -> int:
        if status:
            async with self._db.execute(
                "SELECT COUNT(*) FROM animes WHERE status = ?", (status,)
            ) as cur:
                row = await cur.fetchone()
                return row[0]
        async with self._db.execute("SELECT COUNT(*) FROM animes") as cur:
            row = await cur.fetchone()
            return row[0]

    async def list_generos(self) -> list[dict]:
        async with self._db.execute(
            """
            SELECT g.id, g.nome, COALESCE(g.nome_pt, g.nome) as nome_pt, COUNT(ag.anime_id) as count
            FROM generos g
            LEFT JOIN anime_generos ag ON g.id = ag.genero_id
            GROUP BY g.id
            ORDER BY nome_pt
        """
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_genero_by_nome_pt(self, nome_pt: str) -> dict | None:
        """Lookup case-insensitive (Unicode-safe via Python).

        SQLite LOWER() nao trata acentos/cedilha (ex: 'Ação' != 'AÇÃO'),
        entao carregamos todos os generos (lista pequena) e comparamos em Python.
        """
        async with self._db.execute("SELECT * FROM generos") as cur:
            rows = await cur.fetchall()
        needle = nome_pt.casefold()
        for r in rows:
            row = dict(r)
            if row.get("nome_pt") and row["nome_pt"].casefold() == needle:
                return row
            if row.get("nome") and row["nome"].casefold() == needle:
                return row
        return None

    async def get_animes_by_genero(
        self, genero_nome: str, page: int = 1, limit: int = 30
    ) -> tuple[list[dict], int]:
        offset = (page - 1) * limit
        async with self._db.execute(
            """
            SELECT COUNT(*) FROM animes a
            JOIN anime_generos ag ON a.id = ag.anime_id
            JOIN generos g ON ag.genero_id = g.id
            WHERE g.nome = ?
        """,
            (genero_nome,),
        ) as cur:
            row = await cur.fetchone()
            total = row[0] if row else 0

        async with self._db.execute(
            """
            SELECT a.* FROM animes a
            JOIN anime_generos ag ON a.id = ag.anime_id
            JOIN generos g ON ag.genero_id = g.id
            WHERE g.nome = ?
            ORDER BY a.score DESC NULLS LAST
            LIMIT ? OFFSET ?
        """,
            (genero_nome, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows], total

    async def get_latest_episodes(self, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            """
            SELECT e.*, a.slug, a.titulo, a.imagem, a.tipo
            FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            ORDER BY e.created_at DESC
            LIMIT ?
        """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def upsert_skip_time(
        self,
        anime_id: int,
        ep_numero: int,
        tipo: str,
        start_time: float,
        end_time: float,
    ):
        async with self._write_sem:
            await self._db.execute(
                """
                INSERT INTO skip_times (anime_id, ep_numero, tipo, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(anime_id, ep_numero, tipo) DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time = excluded.end_time
            """,
                (anime_id, ep_numero, tipo, start_time, end_time),
            )
            await self._db.commit()

    async def get_skip_times(self, anime_id: int, ep_numero: int) -> dict:
        async with self._db.execute(
            """
            SELECT tipo, start_time, end_time FROM skip_times
            WHERE anime_id = ? AND ep_numero = ?
        """,
            (anime_id, ep_numero),
        ) as cur:
            rows = await cur.fetchall()
            result = {}
            for r in rows:
                result[r[0]] = {"start": r[1], "end": r[2]}
            return result

    async def get_skip_times_for_anime(self, anime_id: int) -> dict:
        async with self._db.execute(
            """
            SELECT ep_numero, tipo, start_time, end_time FROM skip_times
            WHERE anime_id = ?
            ORDER BY ep_numero, tipo
        """,
            (anime_id,),
        ) as cur:
            rows = await cur.fetchall()
            result = {}
            for r in rows:
                ep = r[0]
                if ep not in result:
                    result[ep] = {}
                result[ep][r[1]] = {"start": r[2], "end": r[3]}
            return result

    # ---- Translation (PT-BR) ----

    async def list_animes_pending_translation(self, limit: int = 500) -> list[dict]:
        """Animes que precisam de traducao PT-BR (titulo_pt ou sinopse_pt ausentes)."""
        async with self._db.execute(
            """
            SELECT id, slug, mal_id, titulo, titulo_en, sinopse, traduzido_em
            FROM animes
            WHERE slug IS NOT NULL
              AND (
                titulo_pt IS NULL
                OR (sinopse IS NOT NULL AND sinopse_pt IS NULL)
              )
              AND (traduzido_em IS NULL OR updated_at > traduzido_em)
            ORDER BY updated_at DESC
            LIMIT ?
        """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def update_translation(
        self,
        anime_id: int,
        titulo_pt: str | None,
        sinopse_pt: str | None,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ):
        """Atualiza titulo_pt e sinopse_pt sem sobrescrever dados Jikan originais."""
        async with self._write_sem:
            await self._db.execute(
                """
                UPDATE animes SET
                    titulo_pt = COALESCE(?, titulo_pt),
                    sinopse_pt = COALESCE(?, sinopse_pt),
                    traduzido_em = datetime('now'),
                    traducao_modelo = ?,
                    traducao_input_tokens = COALESCE(?, traducao_input_tokens),
                    traducao_output_tokens = COALESCE(?, traducao_output_tokens)
                WHERE id = ?
            """,
                (titulo_pt, sinopse_pt, model, input_tokens, output_tokens, anime_id),
            )
            await self._db.commit()

    async def log_translation(
        self,
        anime_id: int,
        provider: str,
        status: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        erro_msg: str | None = None,
    ) -> int:
        started = _utcnow()
        async with self._write_sem:
            cursor = await self._db.execute(
                """
                INSERT INTO translation_log
                    (anime_id, provider, status, input_tokens, output_tokens, started_at, finished_at, erro_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    anime_id,
                    provider,
                    status,
                    input_tokens,
                    output_tokens,
                    started,
                    _utcnow(),
                    erro_msg,
                ),
            )
            await self._db.commit()
            return cursor.lastrowid

    # ---- Jikan metadata (clone) ----

    async def upsert_jikan_metadata(self, anime_id: int, data: dict):
        now = _utcnow()
        async with self._write_sem:
            await self._db.execute(
                """
                INSERT INTO jikan_metadata (
                    anime_id, mal_id, url, approved, title_japanese, title_romaji,
                    type, source, episodes_total, episodes_aired, status_jikan, airing,
                    aired_from, aired_to, duration, rating, season, year,
                    broadcast_day, broadcast_time, studios_json, producers_json,
                    licensors_json, demographics_json, themes_json, relations_json,
                    external_links_json, streaming_json, jikan_fetched_at, jikan_updated_at
                ) VALUES (
                    :anime_id, :mal_id, :url, :approved, :title_japanese, :title_romaji,
                    :type, :source, :episodes_total, :episodes_aired, :status_jikan, :airing,
                    :aired_from, :aired_to, :duration, :rating, :season, :year,
                    :broadcast_day, :broadcast_time, :studios_json, :producers_json,
                    :licensors_json, :demographics_json, :themes_json, :relations_json,
                    :external_links_json, :streaming_json, :jikan_fetched_at, :jikan_updated_at
                )
                ON CONFLICT(anime_id) DO UPDATE SET
                    mal_id = excluded.mal_id,
                    url = excluded.url,
                    approved = excluded.approved,
                    title_japanese = excluded.title_japanese,
                    title_romaji = excluded.title_romaji,
                    type = excluded.type,
                    source = excluded.source,
                    episodes_total = excluded.episodes_total,
                    episodes_aired = excluded.episodes_aired,
                    status_jikan = excluded.status_jikan,
                    airing = excluded.airing,
                    aired_from = excluded.aired_from,
                    aired_to = excluded.aired_to,
                    duration = excluded.duration,
                    rating = excluded.rating,
                    season = excluded.season,
                    year = excluded.year,
                    broadcast_day = excluded.broadcast_day,
                    broadcast_time = excluded.broadcast_time,
                    studios_json = excluded.studios_json,
                    producers_json = excluded.producers_json,
                    licensors_json = excluded.licensors_json,
                    demographics_json = excluded.demographics_json,
                    themes_json = excluded.themes_json,
                    relations_json = excluded.relations_json,
                    external_links_json = excluded.external_links_json,
                    streaming_json = excluded.streaming_json,
                    jikan_updated_at = excluded.jikan_updated_at
            """,
                {**data, "anime_id": anime_id, "jikan_fetched_at": now, "jikan_updated_at": now},
            )
            await self._db.commit()

    async def get_jikan_metadata(self, anime_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM jikan_metadata WHERE anime_id = ?", (anime_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)

    # ---- Job runs ----

    async def log_job_start(self, job_id: str) -> int:
        now = _utcnow()
        async with self._write_sem:
            cursor = await self._db.execute(
                "INSERT INTO job_runs (job_id, started_at, status) VALUES (?, ?, 'running')",
                (job_id, now),
            )
            await self._db.commit()
            return cursor.lastrowid

    async def log_job_end(
        self,
        run_id: int,
        status: str,
        animes_checked: int = 0,
        eps_novos: int = 0,
        cdn_hits: int = 0,
        af_fallbacks: int = 0,
        erro_msg: str = None,
    ):
        now = _utcnow()
        async with self._write_sem:
            await self._db.execute(
                """
                UPDATE job_runs SET
                    finished_at = ?,
                    status = ?,
                    animes_checked = ?,
                    eps_novos = ?,
                    cdn_hits = ?,
                    af_fallbacks = ?,
                    erro_msg = ?
                WHERE id = ?
            """,
                (now, status, animes_checked, eps_novos, cdn_hits, af_fallbacks, erro_msg, run_id),
            )
            await self._db.commit()

    async def get_last_successful_run(self, job_id: str) -> str | None:
        async with self._db.execute(
            """SELECT finished_at FROM job_runs
               WHERE job_id = ? AND status = 'success'
               ORDER BY finished_at DESC LIMIT 1""",
            (job_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    # ---- Missing episodes scan ----

    async def list_animes_without_episodes(self, limit: int = 100) -> list[dict]:
        async with self._db.execute(
            """
            SELECT a.* FROM animes a
            LEFT JOIN episodios e ON e.anime_id = a.id
            WHERE e.id IS NULL AND a.slug IS NOT NULL
            LIMIT ?
        """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def list_animes_with_gaps(self, limit: int = 100) -> list[dict]:
        """Animes com episodes_aired > ultimo_episodio_salvo."""
        async with self._db.execute(
            """
            SELECT a.*, j.episodes_aired,
                   (SELECT MAX(numero) FROM episodios WHERE anime_id = a.id) as last_ep
            FROM animes a
            JOIN jikan_metadata j ON j.anime_id = a.id
            WHERE j.episodes_aired > 0
              AND (SELECT MAX(numero) FROM episodios WHERE anime_id = a.id) < j.episodes_aired
              AND a.slug IS NOT NULL
            LIMIT ?
        """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def list_finished_stale_animes(self, days: int = 14, limit: int = 100) -> list[dict]:
        async with self._db.execute(
            """
            SELECT * FROM animes
            WHERE status = 'finished'
              AND updated_at < datetime('now', ?)
            LIMIT ?
        """,
            (f"-{days} days", limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ---- Context manager ----

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
