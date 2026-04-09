"""
Z-Library source.
Primary  : zlibrary==1.0.2 package (login via email/password)
Fallback : direct HTTPS scraping of z-lib.id / z-library.bz
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import (
    ZLIB_EMAIL, ZLIB_PASSWORD,
    ZLIB_REMIX_USERID, ZLIB_REMIX_USERKEY,
    MAX_FILE_SIZE_MB, ENABLE_ZLIBRARY,
)

logger = logging.getLogger(__name__)

ZLIB_DOMAINS = [
    "https://z-lib.id",
    "https://z-library.bz",
    "https://zlibrary.to",
]


@dataclass
class BookResult:
    title: str
    author: str
    language: str
    format: str
    size_str: str
    size_bytes: int
    book_id: str
    download_url: str
    cover_url: str = ""
    source: str = "Z-Library"
    extra: dict = field(default_factory=dict)


def _parse_size(size_str: str) -> int:
    try:
        s = size_str.strip().upper()
        if "KB" in s:
            return int(float(s.replace("KB", "").strip()) * 1024)
        if "MB" in s:
            return int(float(s.replace("MB", "").strip()) * 1024 * 1024)
        if "GB" in s:
            return int(float(s.replace("GB", "").strip()) * 1024 * 1024 * 1024)
    except Exception:
        pass
    return 0


def _make_client(cookies: dict | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        cookies=cookies or {},
        follow_redirects=True,
        timeout=30,
    )


class _ZLibPackageSearcher:
    """Uses the zlibrary==1.0.2 package for authenticated search."""

    def __init__(self):
        self._zlib = None
        self._ready = False

    async def _init(self):
        if self._ready:
            return
        try:
            from zlibrary import AsyncZlib
            self._zlib = AsyncZlib()
            if ZLIB_EMAIL and ZLIB_PASSWORD:
                await self._zlib.login(ZLIB_EMAIL, ZLIB_PASSWORD)
                logger.info("Z-Library package: logged in")
            else:
                logger.info("Z-Library package: anonymous mode")
            self._ready = True
        except Exception as e:
            logger.warning(f"zlibrary package init failed: {e}")
            self._ready = False

    async def search(self, query: str) -> list[BookResult]:
        await self._init()
        if not self._ready or not self._zlib:
            return []
        try:
            paginator = await self._zlib.search(
                q=query,
                lang="english",
                extensions=["pdf", "epub", "mobi", "fb2", "azw3"],
            )
            raw = await paginator.next()
            results = []
            for book in raw[:15]:
                size_str = getattr(book, "size", "") or ""
                size_bytes = _parse_size(size_str)
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                bid = str(getattr(book, "id", "") or getattr(book, "bookid", ""))
                results.append(BookResult(
                    title=(getattr(book, "title", "") or "Unknown").strip()[:120],
                    author=(getattr(book, "author", "") or "Unknown").strip()[:80],
                    language=getattr(book, "language", "English") or "English",
                    format=(getattr(book, "extension", "pdf") or "pdf").lower(),
                    size_str=size_str or "Unknown",
                    size_bytes=size_bytes,
                    book_id=f"zlib_{bid}",
                    download_url=getattr(book, "download_url", "") or "",
                    cover_url=getattr(book, "cover", "") or "",
                    source="Z-Library",
                    extra={"book_obj": book, "bid": bid},
                ))
            return results
        except Exception as e:
            logger.warning(f"zlibrary package search error: {e}")
            return []

    async def get_download_url(self, book_obj) -> Optional[str]:
        try:
            url = await book_obj.fetch()
            return url
        except Exception as e:
            logger.warning(f"zlibrary fetch error: {e}")
            return None


class _ZLibHTTPSearcher:
    """Direct HTTPS fallback against EAPI."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._domain: Optional[str] = None

    async def _get_client(self) -> tuple[httpx.AsyncClient, str]:
        if self._client and self._domain:
            return self._client, self._domain

        cookies = {}
        if ZLIB_REMIX_USERID and ZLIB_REMIX_USERKEY:
            cookies = {
                "remix_userid": ZLIB_REMIX_USERID,
                "remix_userkey": ZLIB_REMIX_USERKEY,
            }

        client = _make_client(cookies)

        for domain in ZLIB_DOMAINS:
            try:
                r = await client.get(
                    f"{domain}/eapi/book/search",
                    params={"message": "test", "limit": 1},
                    timeout=10,
                )
                if r.status_code < 500:
                    self._client = client
                    self._domain = domain
                    if ZLIB_EMAIL and ZLIB_PASSWORD and not cookies:
                        await self._login(domain, client)
                    return client, domain
            except Exception:
                continue

        self._client = client
        self._domain = ZLIB_DOMAINS[0]
        return client, self._domain

    async def _login(self, domain: str, client: httpx.AsyncClient):
        try:
            r = await client.post(
                f"{domain}/eapi/user/login",
                json={"email": ZLIB_EMAIL, "password": ZLIB_PASSWORD},
                timeout=15,
            )
            data = r.json()
            if data.get("success"):
                logger.info(f"Z-Library HTTP: logged in via {domain}")
        except Exception as e:
            logger.warning(f"Z-Library HTTP login failed: {e}")

    async def search(self, query: str) -> list[BookResult]:
        client, domain = await self._get_client()
        results = []
        try:
            r = await client.get(
                f"{domain}/eapi/book/search",
                params={"message": query, "limit": 20, "lang[]": "english"},
                timeout=20,
            )
            books = r.json().get("books", [])
            for book in books:
                size_str = book.get("filesizeString", "")
                size_bytes = _parse_size(size_str)
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                bid = str(book.get("id", ""))
                results.append(BookResult(
                    title=(book.get("title", "") or "Unknown").strip()[:120],
                    author=(book.get("author", "") or "Unknown").strip()[:80],
                    language=book.get("language", "English") or "English",
                    format=(book.get("extension", "pdf") or "pdf").lower(),
                    size_str=size_str or "Unknown",
                    size_bytes=size_bytes,
                    book_id=f"zlib_{bid}",
                    download_url=book.get("href", "") or "",
                    cover_url=book.get("cover", "") or "",
                    source="Z-Library",
                    extra={
                        "domain": domain,
                        "hash": book.get("hash", ""),
                        "bid": bid,
                    },
                ))
        except Exception as e:
            logger.warning(f"Z-Library HTTP search error on {domain}: {e}")
        return results[:10]

    async def get_download_url(self, bid: str, book_hash: str, domain: str) -> Optional[str]:
        client, _ = await self._get_client()
        for dl_domain in [domain] + [d for d in ZLIB_DOMAINS if d != domain]:
            try:
                r = await client.get(
                    f"{dl_domain}/eapi/book/{bid}/{book_hash}/file/download",
                    timeout=20,
                )
                data = r.json()
                url = data.get("downloadLink") or (data.get("file") or {}).get("downloadLink")
                if url:
                    return url
            except Exception:
                continue
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        client, _ = await self._get_client()
        try:
            async with client.stream("GET", url, timeout=120) as resp:
                cl = int(resp.headers.get("content-length", 0))
                if cl > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None
                chunks, downloaded = [], 0
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Z-Library download error: {e}")
            return None


class ZLibrarySource:
    def __init__(self):
        self._pkg = _ZLibPackageSearcher()
        self._http = _ZLibHTTPSearcher()

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_ZLIBRARY:
            return []
        results = await self._pkg.search(query)
        if not results:
            results = await self._http.search(query)
        return results

    async def get_download_url(self, book: BookResult) -> Optional[str]:
        book_obj = book.extra.get("book_obj")
        if book_obj:
            url = await self._pkg.get_download_url(book_obj)
            if url:
                return url
        bid = book.extra.get("bid", "")
        book_hash = book.extra.get("hash", "")
        domain = book.extra.get("domain", ZLIB_DOMAINS[0])
        return await self._http.get_download_url(bid, book_hash, domain)

    async def download_file(self, url: str) -> Optional[bytes]:
        return await self._http.download_file(url)
