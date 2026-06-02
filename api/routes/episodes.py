"""Shim de retrocompatibilidade. Use anm_db.api.routes.episodes ao inves deste."""

from anm_db.api.routes.episodes import router

__all__ = ["router"]
