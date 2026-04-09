"""
Z-Library source using the zlibrary Python package + cookie-based auth.
Falls back to scraping z-lib.id if credentials are not provided.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import (
    ZLIB_EMAIL, ZLIB_PASSWORD,
    ZLIB_REMIX_USERID, ZLIB_REMIX_USERKEY,
    MAX_FILE_SIZE_MB, ENABLE_ZLIBRARY
)

logger = logging.getLogger(__name__)

ZLIB_DOMAINS = ["https://z-lib.id", "https://z-library.bz"]


@dataclass
class BookResult:
    title: str
    author: str
    language: str
    format: str
    size_str: str
    size_bytes: int
    book_id: str          # unique ID used as /book_<id> command
    download_url: str
    cover_url: str = ""
    source: str = "Z-Library"
    extra: dict = field(default_factory=dict)


class ZLibrarySource:
    def __init__(self):
        self._session: Optional[httpx.AsyncClient] = None
        self._logged_in = False
        self._domain = ZLIB_DOMAINS[0]

    async def _get_session(self) -> httpx.AsyncClient:
        if self._session is None or self._session.is_closed:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
            cookies = {}
            if ZLIB_REMIX_USERID and ZLIB_REMIX_USERKEY:
                cookies["remix_userid"] = ZLIB_REMIX_USERID
                cookies["remix_userkey"] = ZLIB_REMIX_USERKEY
                self._logged_in = True

            self._session = httpx.AsyncClient(
                headers=headers,
                cookies=cookies,
                follow_redirects=True,
                timeout=30,
            )

            if ZLIB_EMAIL and ZLIB_PASSWORD and not self._logged_in:
                await self._login()

        return self._session

    async def _login(self):
        """Login to Z-Library and persist session cookies."""
        for domain in ZLIB_DOMAINS:
            try:
                resp = await self._session.post(
                    f"{domain}/eapi/user/login",
                    json={"email": ZLIB_EMAIL, "password": ZLIB_PASSWORD},
                    timeout=20,
                )
                data = resp.json()
                if data.get("success"):
                    self._logged_in = True
                    self._domain = domain
                    logger.info(f"✅ Logged into Z-Library via {domain}")
                    return
            except Exception as e:
                logger.warning(f"Login failed on {domain}: {e}")
        logger.warning("⚠️ Z-Library login failed on all domains — using anonymous mode")

    @staticmethod
    def _parse_size(size_str: str) -> int:
        """Convert '4.2 MB' → bytes."""
        try:
            size_str = size_str.strip().upper()
            if "KB" in size_str:
                return int(float(size_str.replace("KB", "").strip()) * 1024)
            if "MB" in size_str:
                return int(float(size_str.replace("MB", "").strip()) * 1024 * 1024)
            if "GB" in size_str:
                return int(float(size_str.replace("GB", "").strip()) * 1024 * 1024 * 1024)
        except Exception:
            pass
        return 0

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_ZLIBRARY:
            return []

        session = await self._get_session()
        results: list[BookResult] = []

        for domain in ZLIB_DOMAINS:
            try:
                resp = await session.get(
                    f"{domain}/eapi/book/search",
                    params={"message": query, "limit": 20, "lang[]": "english"},
                    timeout=25,
                )
                data = resp.json()
                books = data.get("books", [])

                for book in books:
                    size_str = book.get("filesizeString", "")
                    size_bytes = self._parse_size(size_str)

                    # Skip oversized files
                    if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                        continue

                    book_id = f"zlib_{book.get('id', '')}"
                    results.append(BookResult(
                        title=book.get("title", "Unknown Title").strip(),
                        author=book.get("author", "Unknown Author").strip(),
                        language=book.get("language", "English"),
                        format=book.get("extension", "pdf").lower(),
                        size_str=size_str or "Unknown",
                        size_bytes=size_bytes,
                        book_id=book_id,
                        download_url=book.get("href", ""),
                        cover_url=book.get("cover", ""),
                        source="Z-Library",
                        extra={"domain": domain, "hash": book.get("hash", "")},
                    ))

                if results:
                    return results[:10]

            except Exception as e:
                logger.warning(f"Z-Library search failed on {domain}: {e}")
                continue

        return results

    async def get_download_url(self, book_id: str, extra: dict) -> Optional[str]:
        """Resolve final direct download URL for a book."""
        raw_id = book_id.replace("zlib_", "")
        domain = extra.get("domain", self._domain)
        book_hash = extra.get("hash", "")

        session = await self._get_session()
        try:
            resp = await session.get(
                f"{domain}/eapi/book/{raw_id}/{book_hash}/file/download",
                timeout=30,
            )
            data = resp.json()
            return data.get("downloadLink") or data.get("file", {}).get("downloadLink")
        except Exception as e:
            logger.error(f"Failed to get download URL for {book_id}: {e}")
            return None

    async def download_file(self, url: str) -> Optional[bytes]:
        """Download file bytes, respecting size limit."""
        session = await self._get_session()
        try:
            async with session.stream("GET", url, timeout=120) as resp:
                content_length = int(resp.headers.get("content-length", 0))
                if content_length > MAX_FILE_SIZE_MB * 1024 * 1024:
                    logger.warning(f"File too large: {content_length} bytes")
                    return None

                chunks = []
                downloaded = 0
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
