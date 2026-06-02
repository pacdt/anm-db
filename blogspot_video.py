"""Shim de retrocompatibilidade. O codigo real vive em `anm_db.scrapers.blogger`."""

from anm_db.scrapers.blogger import (
    _BLOGGER_TOKEN_RE,
    _REGEX_PATTERNS,
    _VideoSourceParser,
    _extract_url_parser,
    _extract_url_regex,
    _fetch_blogger_page,
    _is_blogger_url,
    resolve_blogger_url,
)

__all__ = [
    "resolve_blogger_url",
    "_is_blogger_url",
    "_extract_url_regex",
    "_extract_url_parser",
    "_fetch_blogger_page",
    "_REGEX_PATTERNS",
    "_BLOGGER_TOKEN_RE",
    "_VideoSourceParser",
]
