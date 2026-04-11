"""
LibGen source — works on Render free tier.
Mirror priority: libgen.is > libgen.st > libgen.li > libgen.im
Fixed: libgen.li was returning 404 on /search.php — libgen.is is primary now.
"""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import MAX_FILE_SIZE_MB, ENABLE_LIBGEN
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

# libgen.is is most stable on Render — always try first
LIBGEN_SEARCH_MIRRORS = [
    "https://libgen.is",
    "https://libgen.st",
    "https://libgen.li",
    "https://libgen.im",
]

LIBGEN_DOWNLOAD_MIRRORS = [
    "https://library.lol/main/",
    "https://libgen.is/ads.php?md5=",
    "https://libgen.st/ads.php?md5=",
]

VALID_FORMATS = {"pdf", "epub", "mobi", "djvu", "fb2", "azw3", "doc", "txt"}


def _parse_size(s: str) -> int:
    try:
        s = s.strip().upper().replace(",", "")
        if "KB" in s: return int(float(s.replace("KB","").strip()) * 1024)
        if "MB" in s: return int(float(s.replace("MB","").strip()) * 1024**2)
        if "GB" in s: return int(float(s.replace("GB","").strip()) * 1024**3)
    except Exception:
        pass
    return 0


def _extract_md5(href: str) -> str:
    if not href:
        return ""
    m = re.search(r"md5=([a-fA-F0-9]{32})", href, re.I)
    if m:
        return m.group(1).upper()
    last = href.rstrip("/").split("/")[-1]
    if re.fullmatch(r"[a-fA-F0-9]{32}", last):
        return last.upper()
    return ""


def _parse_rows(soup: BeautifulSoup) -> list[dict]:
    """Parse libgen result table — handles multiple table formats."""
    table = (
        soup.find("table", {"id": "search_table"})
        or soup.find("table", {"class": "catalog"})
        or soup.find("table", {"class": "c"})
    )
    if not table:
        # last resort: biggest table
        tables = soup.find_all("table")
        for t in sorted(tables, key=lambda t: len(t.find_all("tr")), reverse=True):
            if len(t.find_all("tr")) >= 3:
                table = t
                break

    if not table:
        return []

    rows = table.find_all("tr")[1:]
    results = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 8:
            continue
        try:
            # Find title cell — has <a> with md5 in href
            title, md5, author, ext, size_str, lang = "", "", "", "", "", "English"
            for col in cols:
                for a in col.find_all("a", href=True):
                    m5 = _extract_md5(a.get("href", ""))
                    if m5:
                        md5 = m5
                        title = a.get_text(strip=True)
                        break
                if title:
                    break

            if not title and len(cols) > 2:
                a = cols[2].find("a")
                title = a.get_text(strip=True) if a else cols[2].get_text(strip=True)
                if a:
                    md5 = _extract_md5(a.get("href", ""))

            author = cols[1].get_text(strip=True) if len(cols) > 1 else ""

            # ext — scan columns for known format
            for i in [-1, -2, 8, 7]:
                try:
                    cand = cols[i].get_text(strip=True).lower().strip(".")
                    if cand in VALID_FORMATS:
                        ext = cand
                        break
                except Exception:
                    continue

            # size
            for i in [-2, -3, 7, 6]:
                try:
                    cand = cols[i].get_text(strip=True)
                    if re.search(r"\d+\s*(kb|mb|gb)", cand, re.I):
                        size_str = cand
                        break
                except Exception:
                    continue

            if not title or not ext:
                continue

            results.append({
                "title": title[:120],
                "author": author[:80],
                "lang": lang,
                "ext": ext,
                "size_str": size_str,
                "md5": md5,
            })
        except Exception:
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
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
            follow_redirects=True,
            timeout=30,
        )
        self._mirror: Optional[str] = None

    async def _get_mirror(self) -> Optional[str]:
        if self._mirror:
            return self._mirror
        for m in LIBGEN_SEARCH_MIRRORS:
            try:
                r = await self._client.get(f"{m}/", timeout=10)
                if r.status_code < 500:
                    self._mirror = m
                    logger.info(f"LibGen: using mirror {m}")
                    return m
            except Exception as e:
                logger.debug(f"LibGen mirror {m} failed: {e}")
        logger.warning("LibGen: all mirrors unreachable")
        return None

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_LIBGEN:
            return []

        mirror = await self._get_mirror()
        if not mirror:
            return []

        try:
            resp = await self._client.get(
                f"{mirror}/search.php",
                params={"req": query, "res": 25, "column": "def",
                        "phrase": 1, "view": "simple"},
                timeout=25,
            )
            if resp.status_code == 404:
                # This mirror's search URL is wrong — reset and retry with next
                logger.warning(f"LibGen: 404 on {mirror}/search.php — trying alt URL")
                resp = await self._client.get(
                    f"{mirror}/index.php",
                    params={"req": query, "res": 25, "column": "def",
                            "phrase": 1, "view": "simple"},
                    timeout=25,
                )

            if resp.status_code != 200:
                logger.warning(f"LibGen: HTTP {resp.status_code} from {mirror}")
                self._mirror = None
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            rows = _parse_rows(soup)

            # If no results on this mirror, try others
            if not rows:
                logger.warning(f"LibGen: no rows on {mirror} — trying alternatives")
                self._mirror = None
                for alt in LIBGEN_SEARCH_MIRRORS:
                    if alt == mirror:
                        continue
                    try:
                        r2 = await self._client.get(
                            f"{alt}/search.php",
                            params={"req": query, "res": 25, "column": "def", "phrase": 1},
                            timeout=20,
                        )
                        if r2.status_code == 200:
                            rows = _parse_rows(BeautifulSoup(r2.text, "lxml"))
                            if rows:
                                self._mirror = alt
                                logger.info(f"LibGen: switched to {alt}")
                                break
                    except Exception:
                        continue

            results = []
            for row in rows:
                size_bytes = _parse_size(row["size_str"])
                if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    continue
                md5 = row["md5"]
                results.append(BookResult(
                    title=row["title"],
                    author=row["author"],
                    language=row["lang"],
                    format=row["ext"],
                    size_str=row["size_str"] or "Unknown",
                    size_bytes=size_bytes,
                    book_id=f"libgen_{md5 or row['title'][:12].replace(' ','_')}",
                    download_url="",
                    source="Libgen",
                    extra={"md5": md5, "mirror": self._mirror or mirror},
                ))

            logger.info(f"LibGen: {len(results)} results for '{query}'")
            return results[:10]

        except Exception as e:
            logger.warning(f"LibGen search exception: {e}")
            self._mirror = None
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
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True).upper()
                    href = a["href"]
                    if ("GET" in text or "DOWNLOAD" in text) and href.startswith("http"):
                        return href
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if md5.lower() in href.lower() and href.startswith("http"):
                        return href
            except Exception as e:
                logger.debug(f"LibGen DL mirror {dl_mirror}: {e}")
        logger.warning(f"LibGen: no DL URL for md5={md5}")
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
                    return None
                ct = resp.headers.get("content-type", "").lower()
                if "html" in ct:
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
                return data if len(data) > 5000 else None
        except Exception as e:
            logger.error(f"LibGen download error: {e}")
            return None
