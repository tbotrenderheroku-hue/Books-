"""
Z-Library source — Cookie-based HTTP search.

Render free tier blocks z-library.* DNS.
Strategy:
  1. Try all ZLIB_DOMAINS with short timeout
  2. If all fail (DNS blocked), return empty — don't crash
  3. Log a clear warning so owner knows to set cookies or switch source

To make Z-Library work on Render:
  - Set ZLIB_COOKIES env var with your browser cookies (Netscape format)
  - OR set ZLIB_REMIX_USERID + ZLIB_REMIX_USERKEY
  - Even with cookies, DNS must resolve — on Render free tier this may fail.
  - Consider upgrading to Render paid tier OR use a proxy (ZLIB_PROXY env var).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import (
    ZLIB_REMIX_USERID, ZLIB_REMIX_USERKEY,
    ZLIB_COOKIES,
    MAX_FILE_SIZE_MB, ENABLE_ZLIBRARY,
)

logger = logging.getLogger(__name__)

ZLIB_DOMAINS = [
    "https://z-library.bz",
    "https://z-library.id",
    "https://singlelogin.re",
    "https://zlibrary.to",
    "https://z-lib.id",
    "https://z-library.se",
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
        s = str(size_str).strip().upper()
        if "KB" in s:
            return int(float(s.replace("KB", "").strip()) * 1024)
        if "MB" in s:
            return int(float(s.replace("MB", "").strip()) * 1024 * 1024)
        if "GB" in s:
            return int(float(s.replace("GB", "").strip()) * 1024 * 1024 * 1024)
    except Exception:
        pass
    return 0


def _parse_netscape_cookies(cookie_str: str) -> dict:
    cookies = {}
    if not cookie_str:
        return cookies
    for line in cookie_str.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]
            continue
        for pair in line.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies[k.strip()] = v.strip()
    return cookies


def _build_cookies() -> dict:
    if ZLIB_COOKIES:
        parsed = _parse_netscape_cookies(ZLIB_COOKIES)
        if parsed:
            logger.info(f"Z-Library: using Netscape cookies ({len(parsed)} keys)")
            return parsed
    if ZLIB_REMIX_USERID and ZLIB_REMIX_USERKEY:
        logger.info("Z-Library: using remix_userid/userkey cookies")
        return {
            "remix_userid": ZLIB_REMIX_USERID,
            "remix_userkey": ZLIB_REMIX_USERKEY,
        }
    logger.warning("Z-Library: no cookies set — anonymous access (very limited on Render)")
    return {}


class ZLibrarySource:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._domain: Optional[str] = None
        self._cookies = _build_cookies()
        self._dns_blocked = False   # once confirmed blocked, stop retrying

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
            cookies=self._cookies,
            follow_redirects=True,
            timeout=20,
        )

    async def _probe_domains(self) -> bool:
        """Try each domain. Returns True if one is reachable."""
        if self._dns_blocked:
            return False

        client = self._new_client()
        failed = 0

        for domain in ZLIB_DOMAINS:
            try:
                r = await client.get(
                    f"{domain}/eapi/book/search",
                    params={"message": "test", "limit": 1},
                    timeout=10,
                )
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    data = r.json()
                    if "books" in data or "success" in data or "error" in data:
                        self._client = client
                        self._domain = domain
                        logger.info(f"Z-Library: reachable via {domain}")
                        return True
            except Exception as e:
                err = str(e).lower()
                if "name or service not known" in err or "nodename nor servname" in err:
                    failed += 1
                    logger.debug(f"Z-Library DNS blocked for {domain}")
                else:
                    logger.debug(f"Z-Library probe failed {domain}: {e}")
                continue

        if failed == len(ZLIB_DOMAINS):
            self._dns_blocked = True
            logger.warning(
                "Z-Library: ALL domains DNS-blocked (Render free tier restriction). "
                "Results will only come from LibGen + Open Library. "
                "To fix: upgrade Render plan or set up a proxy."
            )
        return False

    async def search(self, query: str, page: int = 1) -> list[BookResult]:
        if not ENABLE_ZLIBRARY:
            return []
        if self._dns_blocked:
            return []

        # Re-probe if not connected
        if not (self._client and self._domain):
            reachable = await self._probe_domains()
            if not reachable:
                return []

        results = []
        try:
            params: dict = {"message": query, "limit": 20, "page": page}
            if self._cookies:
                params["lang[]"] = "english"

            r = await self._client.get(
                f"{self._domain}/eapi/book/search",
                params=params,
                timeout=25,
            )
            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                logger.warning(
                    f"Z-Library: non-JSON response (status={r.status_code}) "
                    "— cookies may be expired"
                )
                self._client = None
                self._domain = None
                return []

            data = r.json()
            books = data.get("books", [])
            if not books and "error" in data:
                logger.warning(f"Z-Library API error: {data.get('error')}")
                return []

            for book in books:
                size_str = str(book.get("filesizeString", "") or book.get("filesize", "") or "")
                size_bytes = _parse_size(size_str)
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                bid = str(book.get("id", ""))
                book_hash = book.get("hash", "")
                href = book.get("href", "") or ""
                if href and not href.startswith("http"):
                    href = f"{self._domain}{href}"

                results.append(BookResult(
                    title=(book.get("title", "") or "Unknown").strip()[:120],
                    author=(book.get("author", "") or "Unknown").strip()[:80],
                    language=book.get("language", "English") or "English",
                    format=(book.get("extension", "pdf") or "pdf").lower(),
                    size_str=size_str or "Unknown",
                    size_bytes=size_bytes,
                    book_id=f"zlib_{bid}",
                    download_url=href,
                    cover_url=book.get("cover", "") or "",
                    source="Z-Library",
                    extra={"domain": self._domain, "hash": book_hash, "bid": bid},
                ))
        except Exception as e:
            logger.warning(f"Z-Library search error: {e}")
            self._client = None
            self._domain = None

        logger.info(f"Z-Library: {len(results)} results for '{query}'")
        return results[:10]

    async def get_download_url(self, book_id: str, extra: dict) -> Optional[str]:
        if self._dns_blocked:
            return None
        bid = extra.get("bid", "")
        book_hash = extra.get("hash", "")
        preferred_domain = extra.get("domain", ZLIB_DOMAINS[0])
        if not bid:
            return None

        if not (self._client and self._domain):
            if not await self._probe_domains():
                return None

        for dl_domain in [preferred_domain] + [d for d in ZLIB_DOMAINS if d != preferred_domain]:
            try:
                if book_hash:
                    url = f"{dl_domain}/eapi/book/{bid}/{book_hash}/file/download"
                else:
                    url = f"{dl_domain}/eapi/book/{bid}/file/download"
                r = await self._client.get(url, timeout=20)
                if r.status_code != 200:
                    continue
                data = r.json()
                link = (
                    data.get("downloadLink")
                    or (data.get("file") or {}).get("downloadLink")
                    or data.get("url")
                )
                if link:
                    return link
            except Exception as e:
                logger.debug(f"Z-Library DL URL failed ({dl_domain}): {e}")
                continue
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        if self._dns_blocked or not self._client:
            return None
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
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
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Z-Library download error: {e}")
            return None
