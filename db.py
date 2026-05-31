import os
import asyncio
import aiosqlite
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("DB")

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS animes (
    id            INTEGER PRIMARY KEY,
    mal_id        INTEGER,
    slug          TEXT NOT NULL UNIQUE,
    tipo          TEXT NOT NULL,
    titulo        TEXT,
    titulo_en     TEXT,
    titulo_jp     TEXT,
    imagem        TEXT,
    score         REAL,
    sinopse       TEXT,
    trailer_url   TEXT,
    status        TEXT,
    next_check_at TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS generos (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE
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
    url_cdn     TEXT,
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

CREATE INDEX IF NOT EXISTS idx_episodios_anime ON episodios(anime_id);
CREATE INDEX IF NOT EXISTS idx_animes_status   ON animes(status);
CREATE INDEX IF NOT EXISTS idx_animes_updated  ON animes(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_animes_check    ON animes(next_check_at) WHERE next_check_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""

MIGRATIONS = []


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("DB_PATH", "anm.db")
        self._db = None
        self._write_sem = asyncio.Semaphore(1)

    async def connect(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.execute("PRAGMA foreign_keys=ON")

    async def close(self):
        if self._db:
            await self._db.close()

    async def init_db(self):
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
            (SCHEMA_VERSION,)
        )

    async def _get_schema_version(self) -> int:
        async with self._db.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1") as cur:
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
        for i, sql in enumerate(MIGRATIONS[current:], start=current + 1):
            await self._db.execute(sql)
            await self._db.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (i,)
            )
            logger.info(f"Migracao {i} aplicada: {sql[:60]}...")

    async def upsert_anime(self, data: dict) -> int:
        now = _utcnow()
        async with self._write_sem:
            await self._db.execute("""
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
            """, {
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
            })
            await self._db.commit()

            async with self._db.execute("SELECT id FROM animes WHERE slug = ?", (data["slug"],)) as cur:
                row = await cur.fetchone()
                return row[0]

    async def upsert_genero(self, nome: str) -> int:
        async with self._write_sem:
            await self._db.execute(
                "INSERT OR IGNORE INTO generos (nome) VALUES (?)",
                (nome,)
            )
            await self._db.commit()
            async with self._db.execute("SELECT id FROM generos WHERE nome = ?", (nome,)) as cur:
                row = await cur.fetchone()
                return row[0]

    async def link_anime_genero(self, anime_id: int, genero_id: int):
        async with self._write_sem:
            await self._db.execute(
                "INSERT OR IGNORE INTO anime_generos (anime_id, genero_id) VALUES (?, ?)",
                (anime_id, genero_id)
            )

    async def upsert_episodio(self, anime_id: int, numero: int, titulo: str = None,
                               url_cdn: str = None, url_af: str = None, fonte_ativa: str = "cdn"):
        async with self._write_sem:
            await self._db.execute("""
                INSERT INTO episodios (anime_id, numero, titulo, url_cdn, url_af, fonte_ativa)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(anime_id, numero) DO UPDATE SET
                    titulo = COALESCE(excluded.titulo, episodios.titulo),
                    url_cdn = COALESCE(excluded.url_cdn, episodios.url_cdn),
                    url_af = COALESCE(excluded.url_af, episodios.url_af),
                    fonte_ativa = excluded.fonte_ativa
            """, (anime_id, numero, titulo, url_cdn, url_af, fonte_ativa))
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

    async def get_ongoing_due(self) -> list[dict]:
        now = _utcnow()
        async with self._db.execute(
            "SELECT * FROM animes WHERE next_check_at IS NOT NULL AND next_check_at <= ?",
            (now,)
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
                [next_time] + anime_ids
            )
            await self._db.commit()

    async def get_episodios_paginados(self, slug: str, page: int = 1, limit: int = 50) -> list[dict]:
        offset = (page - 1) * limit
        async with self._db.execute("""
            SELECT e.* FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            WHERE a.slug = ?
            ORDER BY e.numero ASC
            LIMIT ? OFFSET ?
        """, (slug, limit, offset)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_ultimo_episodio(self, slug: str) -> int:
        async with self._db.execute("""
            SELECT MAX(e.numero) FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            WHERE a.slug = ?
        """, (slug,)) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] else 0

    async def get_episodios_count(self, slug: str) -> int:
        async with self._db.execute("""
            SELECT COUNT(*) FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            WHERE a.slug = ?
        """, (slug,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

    async def get_generos_by_slug(self, slug: str) -> list[str]:
        async with self._db.execute("""
            SELECT g.nome FROM generos g
            JOIN anime_generos ag ON g.id = ag.genero_id
            JOIN animes a ON ag.anime_id = a.id
            WHERE a.slug = ?
        """, (slug,)) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def list_animes_paginado(self, page: int = 1, limit: int = 30,
                                   status: str = None, search: str = None) -> list[dict]:
        conditions = []
        params = []
        if status:
            conditions.append("a.status = ?")
            params.append(status)
        if search:
            conditions.append("(a.titulo LIKE ? OR a.titulo_en LIKE ? OR a.slug LIKE ?)")
            params.extend([f"%{search}%"] * 3)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * limit

        async with self._db.execute(f"""
            SELECT a.* FROM animes a
            {where}
            ORDER BY a.updated_at DESC
            LIMIT ? OFFSET ?
        """, params + [limit, offset]) as cur:
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
        async with self._db.execute("""
            SELECT g.id, g.nome, COUNT(ag.anime_id) as count
            FROM generos g
            LEFT JOIN anime_generos ag ON g.id = ag.genero_id
            GROUP BY g.id
            ORDER BY g.nome
        """) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_animes_by_genero(self, genero_slug: str, page: int = 1, limit: int = 30) -> tuple[list[dict], int]:
        offset = (page - 1) * limit
        async with self._db.execute("""
            SELECT COUNT(*) FROM animes a
            JOIN anime_generos ag ON a.id = ag.anime_id
            JOIN generos g ON ag.genero_id = g.id
            WHERE g.nome = ?
        """, (genero_slug,)) as cur:
            row = await cur.fetchone()
            total = row[0] if row else 0

        async with self._db.execute("""
            SELECT a.* FROM animes a
            JOIN anime_generos ag ON a.id = ag.anime_id
            JOIN generos g ON ag.genero_id = g.id
            WHERE g.nome = ?
            ORDER BY a.score DESC NULLS LAST
            LIMIT ? OFFSET ?
        """, (genero_slug, limit, offset)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows], total

    async def get_latest_episodes(self, limit: int = 50) -> list[dict]:
        async with self._db.execute("""
            SELECT e.*, a.slug, a.titulo, a.imagem, a.tipo
            FROM episodios e
            JOIN animes a ON e.anime_id = a.id
            ORDER BY e.created_at DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def upsert_skip_time(self, anime_id: int, ep_numero: int, tipo: str,
                                start_time: float, end_time: float):
        async with self._write_sem:
            await self._db.execute("""
                INSERT INTO skip_times (anime_id, ep_numero, tipo, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(anime_id, ep_numero, tipo) DO UPDATE SET
                    start_time = excluded.start_time,
                    end_time = excluded.end_time
            """, (anime_id, ep_numero, tipo, start_time, end_time))
            await self._db.commit()

    async def get_skip_times(self, anime_id: int, ep_numero: int) -> dict:
        async with self._db.execute("""
            SELECT tipo, start_time, end_time FROM skip_times
            WHERE anime_id = ? AND ep_numero = ?
        """, (anime_id, ep_numero)) as cur:
            rows = await cur.fetchall()
            result = {}
            for r in rows:
                result[r[0]] = {"start": r[1], "end": r[2]}
            return result

    async def get_skip_times_for_anime(self, anime_id: int) -> dict:
        async with self._db.execute("""
            SELECT ep_numero, tipo, start_time, end_time FROM skip_times
            WHERE anime_id = ?
            ORDER BY ep_numero, tipo
        """, (anime_id,)) as cur:
            rows = await cur.fetchall()
            result = {}
            for r in rows:
                ep = r[0]
                if ep not in result:
                    result[ep] = {}
                result[ep][r[1]] = {"start": r[2], "end": r[3]}
            return result

    async def log_job_start(self, job_id: str) -> int:
        now = _utcnow()
        async with self._write_sem:
            cursor = await self._db.execute(
                "INSERT INTO job_runs (job_id, started_at, status) VALUES (?, ?, 'running')",
                (job_id, now)
            )
            await self._db.commit()
            return cursor.lastrowid

    async def log_job_end(self, run_id: int, status: str, animes_checked: int = 0,
                          eps_novos: int = 0, cdn_hits: int = 0, af_fallbacks: int = 0,
                          erro_msg: str = None):
        now = _utcnow()
        async with self._write_sem:
            await self._db.execute("""
                UPDATE job_runs SET
                    finished_at = ?,
                    status = ?,
                    animes_checked = ?,
                    eps_novos = ?,
                    cdn_hits = ?,
                    af_fallbacks = ?,
                    erro_msg = ?
                WHERE id = ?
            """, (now, status, animes_checked, eps_novos, cdn_hits, af_fallbacks, erro_msg, run_id))
            await self._db.commit()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
