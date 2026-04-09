"""
Anna's Archive source.
Render free tier blocks annas-archive.* DNS — so this source is disabled by default.
No crash, no spam — just silently returns empty on DNS failure.
"""

import logging
from typing import Optional
from .zlibrary_source import BookResult
from config import ENABLE_ANNAS

logger = logging.getLogger(__name__)


class AnnasArchiveSource:
    """Stub — Anna's Archive is DNS-blocked on Render free tier."""

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_ANNAS:
            return []
        # Silently return empty — DNS blocked on Render free tier
        # No warning spam on every search
        return []

    async def get_download_url(self, md5: str, domain: str) -> Optional[str]:
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        return None
