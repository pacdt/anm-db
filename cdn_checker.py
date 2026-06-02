"""Shim de retrocompatibilidade. O codigo real vive em `anm_db.scrapers.cdn`."""

from anm_db.scrapers.cdn import (
    CDN_DOMAINS,
    CDN_TIMEOUT,
    build_url,
    check_cdn_episode,
    format_ep,
    head_request,
)

__all__ = [
    "CDN_DOMAINS",
    "CDN_TIMEOUT",
    "build_url",
    "check_cdn_episode",
    "format_ep",
    "head_request",
]
