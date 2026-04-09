"""
Project Gutenberg source — 70,000+ free public domain books.
Uses Gutendex API (gutendex.com) — accessible from Render.
"""

import logging
from typing import Optional

import httpx

from config import MAX_FILE_SIZE_MB, ENABLE_GUTENBERG
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)


class GutenbergSource:
    API = "https://gutendex.com/books"

    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "BookFinderBot/2.0"},
            follow_redirects=True,
            timeout=20,
        )

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_GUTENBERG:
            return []
        try:
            resp = await self._client.get(
                self.API,
                params={"search": query, "mime_type": "application/pdf"},
                timeout=15,
            )
            data = resp.json()
            results = []
            for book in data.get("results", [])[:5]:
                formats = book.get("formats", {})
                # Pick best format: PDF > EPUB > TXT
                dl_url = ""
                fmt = ""
                for f, url in [
                    ("pdf", formats.get("application/pdf")),
                    ("epub", formats.get("application/epub+zip")),
                    ("txt", formats.get("text/plain")),
                ]:
                    if url:
                        dl_url = url
                        fmt = f
                        break
                if not dl_url:
                    continue
                authors = ", ".join(a.get("name", "") for a in book.get("authors", []))
                bid = str(book.get("id", ""))
                cover = formats.get("image/jpeg", "")
                results.append(BookResult(
                    title=(book.get("title") or "Unknown")[:120],
                    author=authors or "Unknown",
                    language="English",
                    format=fmt,
                    size_str="Free",
                    size_bytes=0,
                    book_id=f"gutenberg_{bid}",
                    download_url=dl_url,
                    cover_url=cover,
                    source="Project Gutenberg",
                    extra={},
                ))
            return results
        except Exception as e:
            logger.warning(f"Gutenberg search error: {e}")
            return []

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=60) as resp:
                if resp.status_code != 200:
                    return None
                chunks, downloaded = [], 0
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Gutenberg download error: {e}")
            return None
