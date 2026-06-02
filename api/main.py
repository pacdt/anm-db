"""Shim de retrocompatibilidade. Use anm_db.api ao inves deste."""

from anm_db.api.main import app
from anm_db.api.deps import close_db, get_db, init_db

__all__ = ["app", "close_db", "get_db", "init_db"]
