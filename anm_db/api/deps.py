"""
Dependency injection para a API.

Mantem uma instancia singleton de DatabaseManager reutilizada em todas
as requests (aiosqlite e thread-safe com WAL).
"""

from __future__ import annotations

from anm_db.repository.database import DatabaseManager

_db_instance: DatabaseManager | None = None


async def get_db() -> DatabaseManager:
    """Dependency que retorna a instancia singleton do DB."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
        await _db_instance.connect()
    return _db_instance


async def init_db() -> None:
    """Inicializa o DB no startup da API (idempotente)."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
        await _db_instance.init_db()


async def close_db() -> None:
    """Fecha o DB no shutdown da API."""
    global _db_instance
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None
