"""Shim de retrocompatibilidade. Use anm_db.api.routes.genres ao inves deste."""

from anm_db.api.routes.genres import router

__all__ = ["router"]
