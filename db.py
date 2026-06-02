"""
Shim de retrocompatibilidade.

O codigo real vive em `anm_db.repository.database`.
Este arquivo existe para que imports legados (`from db import DatabaseManager`)
continuem funcionando durante a transicao.
"""

from anm_db.repository.database import (
    DatabaseManager,
    MIGRATIONS,
    SCHEMA_SQL,
    SCHEMA_VERSION,
    _utcnow,
)

__all__ = ["DatabaseManager", "MIGRATIONS", "SCHEMA_SQL", "SCHEMA_VERSION", "_utcnow"]
