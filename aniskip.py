"""Shim de retrocompatibilidade. O codigo real vive em `anm_db.scrapers.aniskip`."""

from anm_db.scrapers.aniskip import (
    ANISKIP_BASE,
    ANISKIP_TIMEOUT,
    fetch_and_save_skip_times,
    fetch_skip_times,
)

__all__ = [
    "ANISKIP_BASE",
    "ANISKIP_TIMEOUT",
    "fetch_and_save_skip_times",
    "fetch_skip_times",
]
