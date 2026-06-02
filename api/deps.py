"""Shim de retrocompatibilidade. Use anm_db.api.deps ao inves deste."""

from anm_db.api.deps import close_db, get_db, init_db

__all__ = ["close_db", "get_db", "init_db"]
