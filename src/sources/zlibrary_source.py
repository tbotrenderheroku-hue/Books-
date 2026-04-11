"""
Z-Library source — Cookie-based HTTP search with DNS-over-HTTPS bypass.

Render free tier blocks z-library.* DNS resolution.
Fix: Use Google DNS-over-HTTPS (DoH) to resolve the IP, then connect
     directly to the IP with the Host header set — bypasses Render's DNS block.

Requirements:
  - Set ZLIB_COOKIES env var (Netscape format from browser)
  - OR set ZLIB_REMIX_USERID + ZLIB_REMIX_USERKEY
"""

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import (
    ZLIB_REMIX_USERID, ZLIB_REMIX_USERKEY,
    ZLIB_COOKIES, MAX_FILE_SIZE_MB, ENABLE_ZLIBRARY,
)

logger = logging.getLogger(__name__)

# Domain priority — bz and id are most stable
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
            logger.info(f"Z-Library: loaded {len(parsed)} cookies from ZLIB_COOKIES env")
            return parsed
    if ZLIB_REMIX_USERID and ZLIB_REMIX_USERKEY:
        logger.info("Z-Library: using remix_userid/userkey cookies")
        return {
            "remix_userid": ZLIB_REMIX_USERID,
            "remix_userkey": ZLIB_REMIX_USERKEY,
        }
    logger.warning("Z-Library: no cookies set — set ZLIB_COOKIES env var for authenticated access")
    return {}


async def _resolve_via_doh(hostname: str) -> Optional[str]:
    """
    Resolve hostname IP via DNS-over-HTTPS.
    This bypasses Render free tier's DNS blocking for z-library domains.
    """
    doh_client = httpx.AsyncClient(
        headers={
            "Accept": "application/dns-json",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=8,
    )
    try:
        for doh_url in DOH_URLS:
            try:
                r = await doh_client.get(
                    doh_url,
                    params={"name": hostname, "type": "A"},
                )
                data = r.json()
                answers = data.get("Answer", [])
                for ans in answers:
                    if ans.get("type") == 1:  # A record = IPv4
                        ip = ans.get("data", "").strip()
                        if ip:
                            logger.info(f"Z-Library DoH resolved {hostname} → {ip}")
                            return ip
            except Exception as e:
                logger.debug(f"DoH {doh_url} failed for {hostname}: {e}")
                continue
    finally:
        await doh_client.aclose()
    return None


class ZLibrarySource:
    def __init__(self):
        self._cookies = _build_cookies()
        self._working_domain: Optional[str] = None   # e.g. "z-library.bz"
        self._working_ip: Optional[str] = None       # resolved IP
        self._client: Optional[httpx.AsyncClient] = None
        self._failed = False  # give up after all domains exhausted

    def _make_client(self, domain: str, ip: Optional[str]) -> httpx.AsyncClient:
        """
        Build client. If IP is known, use it as base_url and set Host header
        so we bypass DNS entirely.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Host": domain,
            "Referer": f"https://{domain}/",
            "Origin": f"https://{domain}",
        }
        if ip:
            # Connect to IP directly; Host header tells server which vhost
            base = f"https://{ip}"
        else:
            base = f"https://{domain}"

        return httpx.AsyncClient(
            base_url=base,
            headers=headers,
            cookies=self._cookies,
            follow_redirects=True,
            timeout=25,
            verify=False,  # IP-based connections may fail SSL verification
        )

    async def _probe_and_connect(self) -> bool:
        """Try each domain, resolving via DoH if needed."""
        if self._failed:
            return False

        for domain in ZLIB_DOMAINS:
            ip = await _resolve_via_doh(domain)

            # Try with IP (DoH bypass) first, then plain domain
            for use_ip in ([ip, None] if ip else [None]):
                try:
                    client = self._make_client(domain, use_ip)
                    r = await client.get(
                        "/eapi/book/search",
                        params={"message": "test", "limit": 1},
                        timeout=12,
                    )
                    ct = r.headers.get("content-type", "")
                    if r.status_code == 200 and "json" in ct:
                        data = r.json()
                        if "books" in data or "error" in data or "success" in data:
                            self._working_domain = domain
                            self._working_ip = use_ip
                            self._client = client
                            mode = f"IP={use_ip}" if use_ip else "DNS"
                            logger.info(f"Z-Library: connected to {domain} via {mode}")
                            return True
                    await client.aclose()
                except Exception as e:
                    logger.debug(f"Z-Library probe {domain} (ip={use_ip}): {e}")
                    continue

        self._failed = True
        logger.warning(
            "Z-Library: all domains unreachable (DNS blocked + DoH also failed). "
            "zlib=0 results expected. Check ZLIB_COOKIES and domain availability."
        )
        return False

    async def _get_client(self) -> Optional[httpx.AsyncClient]:
        if self._client:
            return self._client
        if self._failed:
            return None
        ok = await self._probe_and_connect()
        return self._client if ok else None

    async def search(self, query: str, page: int = 1) -> list[BookResult]:
        if not ENABLE_ZLIBRARY:
            return []

        client = await self._get_client()
        if not client:
            return []

        results = []
        try:
            params: dict = {"message": query, "limit": 20, "page": page}
            if self._cookies:
                params["lang[]"] = "english"

            r = await client.get("/eapi/book/search", params=params, timeout=25)
            ct = r.headers.get("content-type", "")

            if "json" not in ct:
                logger.warning(
                    f"Z-Library: non-JSON response (status={r.status_code}) "
                    "— cookies may be expired or invalid"
                )
                # Reset — will re-probe next time
                self._client = None
                self._working_domain = None
                return []

            data = r.json()
            if "error" in data and "books" not in data:
                logger.warning(f"Z-Library API error: {data.get('error')}")
                return []

            books = data.get("books", [])
            for book in books:
                size_str = str(book.get("filesizeString") or book.get("filesize") or "")
                size_bytes = _parse_size(size_str)
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                bid = str(book.get("id", ""))
                book_hash = book.get("hash", "") or ""
                href = book.get("href", "") or ""
                if href and not href.startswith("http"):
                    href = f"https://{self._working_domain}{href}"

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
                    extra={
                        "domain": self._working_domain,
                        "ip": self._working_ip,
                        "hash": book_hash,
                        "bid": bid,
                    },
                ))

        except Exception as e:
            logger.warning(f"Z-Library search error: {e}")
            self._client = None
            self._working_domain = None

        logger.info(f"Z-Library: {len(results)} results for '{query}' page={page}")
        return results[:10]

    async def get_download_url(self, book_id: str, extra: dict) -> Optional[str]:
        bid = extra.get("bid", "")
        book_hash = extra.get("hash", "")
        if not bid:
            return None

        client = await self._get_client()
        if not client:
            return None

        domain = self._working_domain or extra.get("domain", ZLIB_DOMAINS[0])

        endpoints = []
        if book_hash:
            endpoints.append(f"/eapi/book/{bid}/{book_hash}/file/download")
        endpoints.append(f"/eapi/book/{bid}/file/download")

        for endpoint in endpoints:
            try:
                r = await client.get(endpoint, timeout=20)
                if r.status_code != 200:
                    continue
                data = r.json()
                link = (
                    data.get("downloadLink")
                    or (data.get("file") or {}).get("downloadLink")
                    or data.get("url")
                )
                if link:
                    logger.info(f"Z-Library: got download URL for bid={bid}")
                    return link
            except Exception as e:
                logger.debug(f"Z-Library DL URL error ({endpoint}): {e}")

        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        client = await self._get_client()
        if not client:
            return None
        try:
            async with client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
                    logger.warning(f"Z-Library file HTTP {resp.status_code}")
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
