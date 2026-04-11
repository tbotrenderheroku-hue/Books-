"""
LibGen source — PRIMARY downloadable source on Render free tier.
Tries libgen.is, libgen.st, libgen.li with multiple table selectors.
"""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import MAX_FILE_SIZE_MB, ENABLE_LIBGEN
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

LIBGEN_SEARCH_MIRRORS = [
    "https://libgen.is",
    "https://libgen.st",
    "https://libgen.li",
    "https://libgen.im",
]

LIBGEN_DOWNLOAD_MIRRORS = [
    "https://library.lol/main/",
    "https://libgen.li/ads.php?md5=",
    "https://libgen.st/ads.php?md5=",
    "https://libgen.is/ads.php?md5=",
]

VALID_FORMATS = {"pdf", "epub", "mobi", "djvu", "fb2", "azw3", "doc", "txt"}


def _parse_size(size_str: str) -> int:
    try:
        s = size_str.strip().upper().replace(",", "")
        if "KB" in s:
            return int(float(s.replace("KB", "").strip()) * 1024)
        if "MB" in s:
            return int(float(s.replace("MB", "").strip()) * 1024 * 1024)
        if "GB" in s:
            return int(float(s.replace("GB", "").strip()) * 1024 * 1024 * 1024)
    except Exception:
        pass
    return 0


def _extract_md5(href: str) -> str:
    """Extract MD5 hash from libgen URL."""
    if not href:
        return ""
    m = re.search(r"md5=([a-fA-F0-9]{32})", href, re.I)
    if m:
        return m.group(1).upper()
    # /book/index.php?md5= style
    parts = href.rstrip("/").split("/")
    last = parts[-1]
    if re.fullmatch(r"[a-fA-F0-9]{32}", last):
        return last.upper()
    return ""


def _parse_table(soup: BeautifulSoup, mirror: str) -> list[dict]:
    """
    Try multiple table selectors — libgen sites have inconsistent markup.
    Returns list of raw row dicts.
    """
    # Selector priority
    table = (
        soup.find("table", {"id": "search_table"})
        or soup.find("table", {"class": "catalog"})
        or soup.find("table", {"class": "c"})
        or soup.find("table", {"border": "0", "rules": "cols"})
    )

    if not table:
        # Last resort: find any table with 10+ rows
        for t in soup.find_all("table"):
            rows = t.find_all("tr")
            if len(rows) >= 5:
                table = t
                break

    if not table:
        return []

    rows = table.find_all("tr")[1:]  # skip header
    results = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 8:
            continue
        try:
            # Different libgen mirrors have different column orders
            # Try to find title/author/ext/size by scanning cols
            title_tag = None
            md5 = ""
            title = ""
            author = ""
            ext = ""
            size_str = ""
            lang = "English"

            # Find title link (usually contains book page URL with md5)
            for col in cols:
                a = col.find("a", href=True)
                if a:
                    href = a.get("href", "")
                    potential_md5 = _extract_md5(href)
                    if potential_md5:
                        md5 = potential_md5
                        title = a.get_text(strip=True)
                        title_tag = a
                        break

            if not title:
                # fallback: col[2] is usually title on libgen.is
                if len(cols) > 2:
                    a = cols[2].find("a")
                    title = (a.get_text(strip=True) if a else cols[2].get_text(strip=True))
                    if a:
                        md5 = _extract_md5(a.get("href", ""))

            # author is usually col[1]
            author = cols[1].get_text(strip=True) if len(cols) > 1 else "Unknown"

            # extension — usually second-to-last or col[8]
            for i in [8, 7, -2, -1]:
                try:
                    candidate = cols[i].get_text(strip=True).lower().strip(".")
                    if candidate in VALID_FORMATS:
                        ext = candidate
                        break
                except Exception:
                    continue

            # size — usually before extension
            for i in [7, 6, -3, -2]:
                try:
                    candidate = cols[i].get_text(strip=True)
                    if re.search(r"\d+\s*(kb|mb|gb)", candidate, re.I):
                        size_str = candidate
                        break
                except Exception:
                    continue

            # language
            for i in [6, 5]:
                try:
                    candidate = cols[i].get_text(strip=True)
                    if candidate and len(candidate) < 30 and not re.search(r"\d", candidate):
                        lang = candidate
                        break
                except Exception:
                    continue

            if not title or not ext:
                continue

            results.append({
                "title": title,
                "author": author,
                "lang": lang,
                "ext": ext,
                "size_str": size_str,
                "md5": md5,
            })
        except Exception as e:
            logger.debug(f"LibGen row parse error: {e}")
            continue

    return results


class LibgenSource:
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=30,
        )
        self._working_mirror: Optional[str] = None

    async def _get_mirror(self) -> Optional[str]:
        if self._working_mirror:
            return self._working_mirror
        for mirror in LIBGEN_SEARCH_MIRRORS:
            try:
                r = await self._client.get(f"{mirror}/", timeout=10)
                if r.status_code < 500:
                    self._working_mirror = mirror
                    logger.info(f"LibGen: using mirror {mirror}")
                    return mirror
            except Exception as e:
                logger.debug(f"LibGen mirror {mirror} unreachable: {e}")
                continue
        logger.warning("LibGen: all search mirrors unreachable")
        return None

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_LIBGEN:
            return []

        mirror = await self._get_mirror()
        if not mirror:
            return []

        results = []
        try:
            resp = await self._client.get(
                f"{mirror}/search.php",
                params={
                    "req": query,
                    "res": 25,
                    "sort": "def",
                    "sortmode": "ASC",
                    "column": "def",
                    "phrase": 1,
                    "view": "simple",
                },
                timeout=25,
            )

            if resp.status_code != 200:
                logger.warning(f"LibGen search HTTP {resp.status_code} from {mirror}")
                self._working_mirror = None
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            rows = _parse_table(soup, mirror)

            if not rows:
                logger.warning(f"LibGen: no results parsed from {mirror} — trying next mirror")
                self._working_mirror = None
                # Try next mirror immediately
                for alt_mirror in LIBGEN_SEARCH_MIRRORS:
                    if alt_mirror == mirror:
                        continue
                    try:
                        r2 = await self._client.get(
                            f"{alt_mirror}/search.php",
                            params={"req": query, "res": 25, "column": "def", "phrase": 1},
                            timeout=20,
                        )
                        soup2 = BeautifulSoup(r2.text, "lxml")
                        rows = _parse_table(soup2, alt_mirror)
                        if rows:
                            self._working_mirror = alt_mirror
                            logger.info(f"LibGen: switched to {alt_mirror}")
                            break
                    except Exception:
                        continue

            for row in rows:
                ext = row["ext"]
                size_str = row["size_str"]
                size_bytes = _parse_size(size_str)
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                md5 = row["md5"]
                results.append(BookResult(
                    title=row["title"][:120],
                    author=row["author"][:80],
                    language=row["lang"] or "English",
                    format=ext,
                    size_str=size_str or "Unknown",
                    size_bytes=size_bytes,
                    book_id=f"libgen_{md5 or row['title'][:15].replace(' ','_')}",
                    download_url="",
                    source="Libgen",
                    extra={"md5": md5, "mirror": self._working_mirror or mirror},
                ))

            logger.info(f"LibGen: {len(results)} results for '{query}'")
            return results[:10]

        except Exception as e:
            logger.warning(f"LibGen search exception: {e}")
            self._working_mirror = None
            return []

    async def get_download_url(self, md5: str, mirror: str) -> Optional[str]:
        if not md5:
            return None
        for dl_mirror in LIBGEN_DOWNLOAD_MIRRORS:
            try:
                url = f"{dl_mirror}{md5}"
                resp = await self._client.get(url, timeout=20)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                # Find GET / DOWNLOAD link
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True).upper()
                    href = a["href"]
                    if ("GET" in text or "DOWNLOAD" in text) and href.startswith("http"):
                        logger.info(f"LibGen: DL URL from {dl_mirror}")
                        return href
                # Fallback: link containing md5
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if md5.lower() in href.lower() and href.startswith("http"):
                        return href
            except Exception as e:
                logger.debug(f"LibGen DL mirror {dl_mirror} error: {e}")
                continue
        logger.warning(f"LibGen: no DL URL for md5={md5}")
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
                    return None
                ct = resp.headers.get("content-type", "").lower()
                if "html" in ct:
                    logger.warning(f"LibGen: got HTML instead of file from {url}")
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
                data = b"".join(chunks)
                if len(data) < 5000:
                    return None
                return data
        except Exception as e:
            logger.error(f"LibGen download error: {e}")
            return None
