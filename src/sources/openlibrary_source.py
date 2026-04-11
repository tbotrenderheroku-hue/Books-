"""
Open Library + Internet Archive source.
Fixes:
  - 403 on archive.org downloads: add proper session/headers, try EPUB before PDF
  - Validate real available formats via metadata API
  - Skip books requiring login (borrow-only)
"""

import logging
from typing import Optional

import httpx

from config import ENABLE_OPENLIBRARY, MAX_FILE_SIZE_MB
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

PREFERRED_FORMATS = ["epub", "pdf", "txt"]  # EPUB first — less likely to 403


class OpenLibrarySource:
    BASE   = "https://openlibrary.org"
    COVERS = "https://covers.openlibrary.org/b/id"
    ARCHIVE_META = "https://archive.org/metadata"
    ARCHIVE_DL   = "https://archive.org/download"

    def __init__(self):
        self._search_client = httpx.AsyncClient(
            headers={"User-Agent": "BookFinderBot/2.0 (educational)"},
            follow_redirects=True,
            timeout=25,
        )
        # Download client mimics a real browser to avoid 403
        self._dl_client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,application/epub+zip,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://archive.org/",
                "DNT": "1",
            },
            follow_redirects=True,
            timeout=120,
        )

    async def _get_ia_files(self, ia_id: str) -> list[dict]:
        """
        Fetch real file list from archive.org metadata API.
        Only returns files that are publicly downloadable (no borrow-only).
        """
        try:
            r = await self._search_client.get(
                f"{self.ARCHIVE_META}/{ia_id}",
                timeout=15,
            )
            if r.status_code != 200:
                return []
            meta = r.json()

            # Check access — skip items requiring login/borrow
            access = meta.get("metadata", {}).get("access-restricted-item", "false")
            if str(access).lower() == "true":
                return []  # borrow-only — would 403 on download

            files = meta.get("files", [])
            found = []
            for f in files:
                name = f.get("name", "")
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in PREFERRED_FORMATS:
                    continue
                size = int(f.get("size", 0))
                if size < 50_000:  # skip tiny/invalid files
                    continue
                if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                found.append({
                    "format": ext,
                    "url": f"{self.ARCHIVE_DL}/{ia_id}/{name}",
                    "size": size,
                })

            # Sort by preferred format order
            found.sort(key=lambda x: PREFERRED_FORMATS.index(x["format"])
                       if x["format"] in PREFERRED_FORMATS else 99)
            return found

        except Exception as e:
            logger.debug(f"Archive.org metadata failed for {ia_id}: {e}")
            return []

    async def search(self, query: str, page: int = 1) -> list[BookResult]:
        if not ENABLE_OPENLIBRARY:
            return []
        try:
            offset = (page - 1) * 8
            resp = await self._search_client.get(
                f"{self.BASE}/search.json",
                params={
                    "q": query, "limit": 8, "offset": offset,
                    "language": "eng", "has_fulltext": "true",
                    "fields": "key,title,author_name,cover_i,ia",
                },
                timeout=20,
            )
            data = resp.json()
            results = []

            for doc in data.get("docs", []):
                ia_list = doc.get("ia", [])
                if not ia_list:
                    continue
                ia_id = ia_list[0] if isinstance(ia_list, list) else ia_list

                key = doc.get("key", "")
                ol_id = key.replace("/works/", "") if key else ia_id
                cover_id = doc.get("cover_i", "")
                cover_url = f"{self.COVERS}/{cover_id}-M.jpg" if cover_id else ""
                authors = ", ".join(doc.get("author_name", []))
                title = doc.get("title", "Unknown")

                ia_files = await self._get_ia_files(ia_id)
                if not ia_files:
                    continue  # skip borrow-only or missing files

                for ia_file in ia_files[:1]:  # one result per book
                    fmt = ia_file["format"]
                    size_bytes = ia_file["size"]
                    results.append(BookResult(
                        title=title[:120],
                        author=authors or "Unknown",
                        language="English",
                        format=fmt,
                        size_str=_fmt_size(size_bytes),
                        size_bytes=size_bytes,
                        book_id=f"openlibrary_{ol_id}_{fmt}",
                        download_url=ia_file["url"],
                        cover_url=cover_url,
                        source="Open Library",
                        extra={"ia_id": ia_id},
                    ))

            logger.info(f"Open Library: {len(results)} downloadable results for '{query}'")
            return results[:5]

        except Exception as e:
            logger.warning(f"Open Library search error: {e}")
            return []

    async def download_file(self, url: str) -> Optional[bytes]:
        """Download with browser headers to avoid 403."""
        try:
            async with self._dl_client.stream("GET", url, timeout=120) as resp:
                if resp.status_code == 403:
                    logger.warning(f"Archive.org 403 (login required) for {url}")
                    return None
                if resp.status_code != 200:
                    logger.warning(f"Archive.org HTTP {resp.status_code} for {url}")
                    return None

                ct = resp.headers.get("content-type", "").lower()
                if "html" in ct:
                    logger.warning(f"Archive.org returned HTML page instead of file")
                    return None

                cl = int(resp.headers.get("content-length", 0))
                if cl > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None

                chunks, downloaded = [], 0
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)

                file_bytes = b"".join(chunks)

                # Validate file magic bytes
                if url.endswith(".pdf") and not file_bytes.startswith(b"%PDF"):
                    logger.warning("Archive.org: downloaded file is not a valid PDF")
                    return None
                if url.endswith(".epub") and not file_bytes[:4] == b"PK\x03\x04":
                    logger.warning("Archive.org: downloaded file is not a valid EPUB")
                    return None

                return file_bytes

        except Exception as e:
            logger.error(f"Archive.org download error: {e}")
            return None


def _fmt_size(b: int) -> str:
    if b == 0: return "Unknown"
    if b < 1024**2: return f"{b/1024:.0f} KB"
    return f"{b/1024**2:.1f} MB"
