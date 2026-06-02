"""Domain entities (immutable dataclasses mapping 1:1 with DB tables)."""

from anm_db.domain.anime import Anime
from anm_db.domain.episodio import Episodio
from anm_db.domain.skip_time import SkipTime
from anm_db.domain.genero import Genero
from anm_db.domain.jikan_metadata import JikanMetadata
from anm_db.domain.job_run import JobRun
from anm_db.domain.translation_log import TranslationLog

__all__ = [
    "Anime",
    "Episodio",
    "SkipTime",
    "Genero",
    "JikanMetadata",
    "JobRun",
    "TranslationLog",
]
