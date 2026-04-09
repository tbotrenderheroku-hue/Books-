"""
Open Library (openlibrary.org) source — Internet Archive's open book catalog.
"""

import logging
from typing import Optional

import httpx

from config import ENABLE_OPENLIBRARY, MAX_FILE_SIZE_MB
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)


class OpenLibrarySource:
    BASE = "https://openlibrary.org"
    COVERS = "https://covers.openlibrary.org/b/id"

    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "BookFinderBot/1.0"},
            follow_redirects=True,
            timeout=25,
        )

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_OPENLIBRARY:
            return []

        try:
            resp = await self._client.get(
                f"{self.BASE}/search.json",
                params={"q": query, "limit": 10, "language": "eng",
                        "has_fulltext": "true"},
                timeout=20,
            )
            data = resp.json()
            results = []

            for doc in data.get("docs", []):
                if not doc.get("ia"):
                    continue
                ia_id = doc["ia"][0] if isinstance(doc["ia"], list) else doc["ia"]
                key = doc.get("key", "")
                ol_id = key.replace("/works/", "") if key else ia_id

                cover_id = doc.get("cover_i", "")
                cover_url = f"{self.COVERS}/{cover_id}-M.jpg" if cover_id else ""

                authors = ", ".join(doc.get("author_name", []))
                title = doc.get("title", "Unknown")

                results.append(BookResult(
                    title=title[:120],
                    author=authors or "Unknown",
                    language="English",
                    format="pdf",
                    size_str="Unknown",
                    size_bytes=0,
                    book_id=f"openlibrary_{ol_id}",
                    download_url=f"https://archive.org/download/{ia_id}/{ia_id}.pdf",
                    cover_url=cover_url,
                    source="Open Library",
                    extra={"ia_id": ia_id, "ol_id": ol_id},
                ))

            return results[:6]
        except Exception as e:
            logger.warning(f"Open Library search error: {e}")
            return []

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                content_length = int(resp.headers.get("content-length", 0))
                if content_length > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None
                chunks = []
                downloaded = 0
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Open Library download error: {e}")
            return None
