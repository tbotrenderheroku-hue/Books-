"""
Z-Library source — aiohttp + custom DoH DNS resolver.

Problem: Render blocks z-library.* DNS. httpx IP-based connections fail because
         Cloudflare requires correct SNI in TLS handshake (IP ≠ SNI).

Fix: Use aiohttp with a CUSTOM RESOLVER that returns DoH-resolved IPs while
     keeping the original domain name for SSL SNI. This satisfies both:
       - Render's DNS block (we bypass it with DoH)
       - Cloudflare's SNI check (domain name still sent in TLS handshake)
"""

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from config import (
    ZLIB_REMIX_USERID, ZLIB_REMIX_USERKEY,
    ZLIB_COOKIES, MAX_FILE_SIZE_MB, ENABLE_ZLIBRARY,
)

logger = logging.getLogger(__name__)

ZLIB_DOMAINS = [
    "z-library.bz",
    "z-library.id",
    "singlelogin.re",
    "zlibrary.to",
    "z-lib.id",
    "z-library.se",
]

DOH_URLS = [
    "https://dns.google/resolve",
    "https://cloudflare-dns.com/dns-query",
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


def _parse_size(s: str) -> int:
    try:
        s = str(s).strip().upper()
        if "KB" in s: return int(float(s.replace("KB","").strip()) * 1024)
        if "MB" in s: return int(float(s.replace("MB","").strip()) * 1024**2)
        if "GB" in s: return int(float(s.replace("GB","").strip()) * 1024**3)
    except Exception:
        pass
    return 0


def _parse_netscape_cookies(cookie_str: str) -> dict:
    cookies: dict = {}
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
            logger.info(f"Z-Library: loaded {len(parsed)} cookies from ZLIB_COOKIES")
            return parsed
    if ZLIB_REMIX_USERID and ZLIB_REMIX_USERKEY:
        logger.info("Z-Library: using remix_userid + remix_userkey")
        return {"remix_userid": ZLIB_REMIX_USERID, "remix_userkey": ZLIB_REMIX_USERKEY}
    logger.warning("Z-Library: no cookies — set ZLIB_COOKIES env var")
    return {}


# ── Custom aiohttp resolver that uses DoH ────────────────────────────────────

class _DoHResolver(aiohttp.abc.AbstractResolver):
    """
    aiohttp resolver that uses DNS-over-HTTPS (Google/Cloudflare).
    Returns the DoH-resolved IP but keeps original hostname for SNI.
    This bypasses Render's DNS block while satisfying Cloudflare's SNI.
    """

    def __init__(self):
        self._cache: dict[str, str] = {}

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        if host in self._cache:
            ip = self._cache[host]
            return [{"hostname": host, "host": ip, "port": port,
                     "family": family, "proto": 0, "flags": 0}]

        # Try DoH resolution
        for doh_url in DOH_URLS:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        doh_url,
                        params={"name": host, "type": "A"},
                        headers={"Accept": "application/dns-json"},
                        timeout=aiohttp.ClientTimeout(total=6),
                        ssl=True,
                    ) as r:
                        data = await r.json(content_type=None)
                        for ans in data.get("Answer", []):
                            if ans.get("type") == 1:
                                ip = ans["data"].strip()
                                self._cache[host] = ip
                                logger.debug(f"DoH: {host} → {ip}")
                                return [{"hostname": host, "host": ip, "port": port,
                                         "family": family, "proto": 0, "flags": 0}]
            except Exception as e:
                logger.debug(f"DoH {doh_url} failed for {host}: {e}")
                continue

        raise OSError(f"DoH resolution failed for {host} (all DoH servers tried)")

    async def close(self):
        pass


# ── ZLibrarySource ────────────────────────────────────────────────────────────

class ZLibrarySource:
    def __init__(self):
        self._cookies     = _build_cookies()
        self._session: Optional[aiohttp.ClientSession] = None
        self._domain: Optional[str] = None
        self._failed      = False

    def _headers(self, domain: str) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://{domain}/",
            "Origin": f"https://{domain}",
        }

    async def _make_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        resolver  = _DoHResolver()
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            ssl=True,        # keep SSL verification ON — SNI is correct now
            limit=10,
            ttl_dns_cache=300,
        )
        jar = aiohttp.CookieJar()
        self._session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=jar,
            timeout=aiohttp.ClientTimeout(total=30),
        )
        # Inject cookies
        for name, value in self._cookies.items():
            for domain in ZLIB_DOMAINS:
                self._session.cookie_jar.update_cookies(
                    {name: value},
                    response_url=aiohttp.typedefs.StrOrURL(f"https://{domain}/"),
                )
        return self._session

    async def _probe(self) -> bool:
        if self._failed:
            return False
        session = await self._make_session()
        for domain in ZLIB_DOMAINS:
            try:
                async with session.get(
                    f"https://{domain}/eapi/book/search",
                    params={"message": "test", "limit": 1},
                    headers=self._headers(domain),
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as r:
                    ct = r.headers.get("Content-Type", "")
                    if r.status == 200 and "json" in ct:
                        data = await r.json(content_type=None)
                        if "books" in data or "error" in data:
                            self._domain = domain
                            logger.info(f"Z-Library: connected to {domain} (DoH+SNI)")
                            return True
            except Exception as e:
                logger.debug(f"Z-Library probe {domain}: {e}")
                continue
        self._failed = True
        logger.warning("Z-Library: all domains unreachable. Set ZLIB_COOKIES correctly.")
        return False

    async def _get_session_and_domain(self) -> tuple[Optional[aiohttp.ClientSession], Optional[str]]:
        if self._domain and self._session and not self._session.closed:
            return self._session, self._domain
        if self._failed:
            return None, None
        ok = await self._probe()
        return (self._session, self._domain) if ok else (None, None)

    async def search(self, query: str, page: int = 1) -> list[BookResult]:
        if not ENABLE_ZLIBRARY:
            return []
        session, domain = await self._get_session_and_domain()
        if not session or not domain:
            return []

        results = []
        try:
            params: dict = {"message": query, "limit": 20, "page": page}
            if self._cookies:
                params["lang[]"] = "english"

            async with session.get(
                f"https://{domain}/eapi/book/search",
                params=params,
                headers=self._headers(domain),
                timeout=aiohttp.ClientTimeout(total=25),
            ) as r:
                ct = r.headers.get("Content-Type", "")
                if "json" not in ct:
                    logger.warning(
                        f"Z-Library: non-JSON (status={r.status}) "
                        "— cookies expired or invalid"
                    )
                    self._domain = None
                    return []
                data = await r.json(content_type=None)

            if "error" in data and "books" not in data:
                logger.warning(f"Z-Library API: {data.get('error')}")
                return []

            for book in data.get("books", []):
                size_str  = str(book.get("filesizeString") or book.get("filesize") or "")
                size_bytes = _parse_size(size_str)
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                bid        = str(book.get("id", ""))
                book_hash  = book.get("hash", "") or ""
                href       = book.get("href", "") or ""
                if href and not href.startswith("http"):
                    href = f"https://{domain}{href}"

                results.append(BookResult(
                    title=(book.get("title") or "Unknown").strip()[:120],
                    author=(book.get("author") or "Unknown").strip()[:80],
                    language=book.get("language") or "English",
                    format=(book.get("extension") or "pdf").lower(),
                    size_str=size_str or "Unknown",
                    size_bytes=size_bytes,
                    book_id=f"zlib_{bid}",
                    download_url=href,
                    cover_url=book.get("cover") or "",
                    source="Z-Library",
                    extra={"domain": domain, "hash": book_hash, "bid": bid},
                ))

        except Exception as e:
            logger.warning(f"Z-Library search error: {e}")
            self._domain = None

        logger.info(f"Z-Library: {len(results)} results for '{query}' p={page}")
        return results[:10]

    async def get_download_url(self, book_id: str, extra: dict) -> Optional[str]:
        bid        = extra.get("bid", "")
        book_hash  = extra.get("hash", "")
        if not bid:
            return None
        session, domain = await self._get_session_and_domain()
        if not session or not domain:
            return None

        d = extra.get("domain", domain)
        endpoints = []
        if book_hash:
            endpoints.append(f"https://{d}/eapi/book/{bid}/{book_hash}/file/download")
        endpoints.append(f"https://{d}/eapi/book/{bid}/file/download")

        for ep in endpoints:
            try:
                async with session.get(
                    ep,
                    headers=self._headers(d),
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)
                    link = (
                        data.get("downloadLink")
                        or (data.get("file") or {}).get("downloadLink")
                        or data.get("url")
                    )
                    if link:
                        logger.info(f"Z-Library: got DL URL bid={bid}")
                        return link
            except Exception as e:
                logger.debug(f"Z-Library DL URL error {ep}: {e}")

        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        session, domain = await self._get_session_and_domain()
        if not session:
            return None
        d = domain or ZLIB_DOMAINS[0]
        try:
            async with session.get(
                url,
                headers=self._headers(d),
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Z-Library DL HTTP {resp.status}")
                    return None
                cl = int(resp.headers.get("Content-Length", 0))
                if cl > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None
                chunks, downloaded = [], 0
                async for chunk in resp.content.iter_chunked(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Z-Library download error: {e}")
            return None
