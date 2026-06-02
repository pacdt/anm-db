"""Shim de retrocompatibilidade. O codigo real vive em `anm_db.scrapers.jikan`."""

from anm_db.scrapers.jikan import (
    JIKAN_BASE,
    JIKAN_MAX_RETRIES,
    JIKAN_RATE_LIMIT,
    JIKAN_RETRY_DELAY,
    JIKAN_TIMEOUT,
    JikanSync,
)

__all__ = [
    "JIKAN_BASE",
    "JIKAN_MAX_RETRIES",
    "JIKAN_RATE_LIMIT",
    "JIKAN_RETRY_DELAY",
    "JIKAN_TIMEOUT",
    "JikanSync",
]
