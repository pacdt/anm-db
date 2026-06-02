"""Shim de retrocompatibilidade. Use anm_db.api.routes.download ao inves deste."""

from anm_db.api.routes.download import router

__all__ = ["router"]
