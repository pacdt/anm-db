"""Shim de retrocompatibilidade. Use anm_db.api.routes.animes ao inves deste."""

from anm_db.api.routes.animes import router

__all__ = ["router"]
