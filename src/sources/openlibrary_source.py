"""
Open Library + Internet Archive source.
- Searches openlibrary.org for books with Internet Archive availability
- Tries multiple formats: PDF, EPUB, plain text
- Validates format before adding to results (fixes "invalid format" PDF errors)
"""

import logging
from typing import Optional

import httpx

from config import ENABLE_OPENLIBRARY, MAX_FILE_SIZE_MB
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

# Format preference order
PREFERRED_FORMATS = ["pdf", "epub", "txt", "djvu"]


class OpenLibrarySource:
    BASE = "https://openlibrary.org"
    COVERS = "https://covers.openlibrary.org/b/id"
    ARCHIVE_META = "https://archive.org/metadata"

    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "BookFinderBot/2.0 (educational use)"},
            follow_redirects=True,
            timeout=25,
        )

    async def _get_ia_formats(self, ia_id: str) -> list[dict]:
        """
        Query archive.org metadata to find real available file formats.
        Returns list of dicts: {format, url, size}
        Fixes "invalid PDF format" — only returns files that actually exist.
        """
        try:
            r = await self._client.get(f"{self.ARCHIVE_META}/{ia_id}", timeout=15)
            if r.status_code != 200:
                return []
            meta = r.json()
            files = meta.get("files", [])
            results = []
            for f in files:
                name = f.get("name", "")
                fmt = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if fmt not in PREFERRED_FORMATS:
                    continue
                # Skip very small files (likely invalid/placeholder)
                size = int(f.get("size", 0))
                if size < 10_000:  # < 10KB = probably junk
                    continue
                results.append({
                    "format": fmt,
                    "url": f"https://archive.org/download/{ia_id}/{name}",
                    "size": size,
                    "name": name,
                })
            # Sort by preference order
            results.sort(key=lambda x: PREFERRED_FORMATS.index(x["format"])
                         if x["format"] in PREFERRED_FORMATS else 99)
            return results
        except Exception as e:
            logger.debug(f"Archive.org metadata fetch failed for {ia_id}: {e}")
            return []

    async def search(self, query: str, page: int = 1) -> list[BookResult]:
        if not ENABLE_OPENLIBRARY:
            return []

        try:
            offset = (page - 1) * 10
            resp = await self._client.get(
                f"{self.BASE}/search.json",
                params={
                    "q": query,
                    "limit": 10,
                    "offset": offset,
                    "language": "eng",
                    "has_fulltext": "true",
                    "fields": "key,title,author_name,cover_i,ia,language,edition_count",
                },
                timeout=20,
            )
            data = resp.json()
            results = []

            for doc in data.get("docs", []):
                ia_list = doc.get("ia", [])
                if not ia_list:
                    continue
                if isinstance(ia_list, str):
                    ia_list = [ia_list]

                # Use first IA identifier
                ia_id = ia_list[0]
                key = doc.get("key", "")
                ol_id = key.replace("/works/", "") if key else ia_id

                cover_id = doc.get("cover_i", "")
                cover_url = f"{self.COVERS}/{cover_id}-M.jpg" if cover_id else ""
                authors = ", ".join(doc.get("author_name", []))
                title = doc.get("title", "Unknown")

                # Get real available formats from archive.org metadata
                ia_files = await self._get_ia_formats(ia_id)

                if ia_files:
                    # Add one result per format (best first)
                    for ia_file in ia_files[:2]:  # max 2 formats per book
                        fmt = ia_file["format"]
                        size_bytes = ia_file["size"]
                        if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                            continue
                        size_str = _fmt_size(size_bytes)
                        results.append(BookResult(
                            title=title[:120],
                            author=authors or "Unknown",
                            language="English",
                            format=fmt,
                            size_str=size_str,
                            size_bytes=size_bytes,
                            book_id=f"openlibrary_{ol_id}_{fmt}",
                            download_url=ia_file["url"],
                            cover_url=cover_url,
                            source="Open Library",
                            extra={"ia_id": ia_id, "ol_id": ol_id},
                        ))
                else:
                    # Fallback: add with unknown format (archive.org unavailable)
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
        """
        Download from archive.org. Tries the direct URL first.
        If response is HTML (redirect/error page), returns None.
        """
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
                    logger.warning(f"Archive.org download HTTP {resp.status_code} for {url}")
                    return None

                # Validate content type — reject HTML pages served as "PDF"
                ct = resp.headers.get("content-type", "").lower()
                if "html" in ct or "text/plain" in ct and not url.endswith(".txt"):
                    logger.warning(f"Archive.org returned HTML instead of file for {url}")
                    return None

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

                file_bytes = b"".join(chunks)

                # Validate PDF magic bytes — catch "invalid format" errors before Telegram rejects
                if url.endswith(".pdf"):
                    if not file_bytes.startswith(b"%PDF"):
                        logger.warning(f"Archive.org returned invalid PDF (no magic bytes) for {url}")
                        return None

                return file_bytes
        except Exception as e:
            logger.error(f"Open Library/Archive.org download error: {e}")
            return None


def _fmt_size(b: int) -> str:
    if b == 0:
        return "Unknown"
    if b < 1024 ** 2:
        return f"{b/1024:.0f} KB"
    return f"{b/1024**2:.1f} MB"
