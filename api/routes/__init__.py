"""Shim de retrocompatibilidade. Use anm_db.api.routes ao inves deste."""

from anm_db.api.routes import animes, episodes, genres
from anm_db.api.routes.download import router as download

__all__ = ["animes", "episodes", "genres", "download"]
