"""
Project Gutenberg source — free public domain books.
"""

import logging
from typing import Optional

import httpx

from config import ENABLE_GUTENBERG, MAX_FILE_SIZE_MB
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)


class GutenbergSource:
    BASE = "https://gutendex.com"

    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "BookFinderBot/1.0"},
            follow_redirects=True,
            timeout=25,
        )

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_GUTENBERG:
            return []

        try:
            resp = await self._client.get(
                f"{self.BASE}/books/",
                params={"search": query, "languages": "en", "mime_type": "application/pdf"},
                timeout=20,
            )
            data = resp.json()
            results = []
            for book in data.get("results", [])[:8]:
                formats = book.get("formats", {})
                # Pick best format
                dl_url = ""
                ext = ""
                for fmt_key in ("application/pdf", "application/epub+zip", "application/x-mobipocket-ebook"):
                    if fmt_key in formats:
                        dl_url = formats[fmt_key]
                        ext = fmt_key.split("/")[-1].replace("epub+zip", "epub").replace("x-mobipocket-ebook", "mobi")
                        break

                if not dl_url:
                    continue

                authors = ", ".join(a["name"] for a in book.get("authors", []))
                book_id = str(book.get("id", ""))

                results.append(BookResult(
                    title=book.get("title", "Unknown")[:120],
                    author=authors or "Unknown",
                    language="English",
                    format=ext,
                    size_str="Unknown",
                    size_bytes=0,
                    book_id=f"gutenberg_{book_id}",
                    download_url=dl_url,
                    source="Project Gutenberg",
                    extra={"gutenberg_id": book_id},
                ))

            return results
        except Exception as e:
            logger.warning(f"Gutenberg search error: {e}")
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
            logger.error(f"Gutenberg download error: {e}")
            return None
