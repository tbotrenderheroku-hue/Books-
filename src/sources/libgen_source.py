"""
LibGen source — fixed column parsing.
libgen.li structure: col0=ID, col1=Authors, col2=Title, col3=Publisher,
                     col4=Year, col5=Pages, col6=Language, col7=Size, col8=Ext, col9=Mirrors
"""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import MAX_FILE_SIZE_MB, ENABLE_LIBGEN
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

LIBGEN_MIRRORS = [
    "https://libgen.is",
    "https://libgen.st",
    "https://libgen.li",
    "https://libgen.im",
]

LIBGEN_DL_MIRRORS = [
    "https://library.lol/main/",
    "https://libgen.is/ads.php?md5=",
    "https://libgen.st/ads.php?md5=",
]

VALID_EXTS = {"pdf", "epub", "mobi", "djvu", "fb2", "azw3", "doc", "txt"}


def _parse_size(s: str) -> int:
    try:
        s = s.strip().upper().replace(",", "")
        if "KB" in s: return int(float(s.replace("KB","").strip()) * 1024)
        if "MB" in s: return int(float(s.replace("MB","").strip()) * 1024**2)
        if "GB" in s: return int(float(s.replace("GB","").strip()) * 1024**3)
    except Exception:
        pass
    return 0


def _get_md5(href: str) -> str:
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
    """
    Parse libgen result table.
    Fixed: always use col[2] for title, col[1] for author (standard libgen layout).
    col[0] is always the numeric ID — was being picked up as title before.
    """
    table = (
        soup.find("table", {"id": "search_table"})
        or soup.find("table", {"class": "catalog"})
        or soup.find("table", {"class": "c"})
    )
    if not table:
        for t in soup.find_all("table"):
            if len(t.find_all("tr")) >= 4:
                table = t
                break
    if not table:
        return []

    rows = table.find_all("tr")[1:]  # skip header row
    results = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 9:
            continue
        try:
            # col[1] = Authors
            author = cols[1].get_text(strip=True)

            # col[2] = Title (with link)
            title_col = cols[2]
            title_tag = title_col.find("a", href=True)
            title = title_tag.get_text(strip=True) if title_tag else title_col.get_text(strip=True)

            # MD5 — from title link OR from mirror links in col[9] (libgen.li)
            md5 = ""
            if title_tag:
                md5 = _get_md5(title_tag.get("href", ""))
            if not md5 and len(cols) > 9:
                for a in cols[9].find_all("a", href=True):
                    md5 = _get_md5(a["href"])
                    if md5:
                        break
            if not md5 and len(cols) > 10:
                for a in cols[10].find_all("a", href=True):
                    md5 = _get_md5(a["href"])
                    if md5:
                        break

            # col[6] = Language
            lang = cols[6].get_text(strip=True) or "English"

            # col[7] = Size
            size_str = cols[7].get_text(strip=True)

            # col[8] = Extension
            ext = cols[8].get_text(strip=True).lower().strip(".")

            if not title or ext not in VALID_EXTS:
                continue

            results.append({
                "title":    title[:120],
                "author":   author[:80],
                "lang":     lang,
                "ext":      ext,
                "size_str": size_str,
                "md5":      md5,
            })
        except Exception as e:
            logger.debug(f"LibGen row error: {e}")
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
                "Accept": "text/html,*/*;q=0.8",
            },
            follow_redirects=True,
            timeout=30,
        )
        self._mirror: Optional[str] = None

    async def _get_mirror(self) -> Optional[str]:
        if self._mirror:
            return self._mirror
        for m in LIBGEN_MIRRORS:
            try:
                r = await self._client.get(f"{m}/", timeout=10)
                if r.status_code < 500:
                    self._mirror = m
                    logger.info(f"LibGen: using mirror {m}")
                    return m
            except Exception as e:
                logger.debug(f"LibGen {m}: {e}")
        logger.warning("LibGen: all mirrors unreachable")
        return None

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_LIBGEN:
            return []
        mirror = await self._get_mirror()
        if not mirror:
            return []

        rows = []
        # Try search.php first, then index.php
        for path in ["/search.php", "/index.php"]:
            try:
                resp = await self._client.get(
                    f"{mirror}{path}",
                    params={"req": query, "res": 25, "column": "def", "phrase": 1, "view": "simple"},
                    timeout=25,
                )
                if resp.status_code == 200:
                    rows = _parse_rows(BeautifulSoup(resp.text, "lxml"))
                    if rows:
                        break
                elif resp.status_code == 404:
                    continue
            except Exception as e:
                logger.debug(f"LibGen {mirror}{path}: {e}")

        # If still no rows, try other mirrors
        if not rows:
            self._mirror = None
            for alt in LIBGEN_MIRRORS:
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
            results.append(BookResult(
                title    = row["title"],
                author   = row["author"],
                language = row["lang"],
                format   = row["ext"],
                size_str = row["size_str"] or "Unknown",
                size_bytes = size_bytes,
                book_id  = f"libgen_{row['md5'] or row['title'][:12].replace(' ','_')}",
                download_url = "",
                source   = "Libgen",
                extra    = {"md5": row["md5"], "mirror": self._mirror or mirror},
            ))

        logger.info(f"LibGen: {len(results)} results for '{query}'")
        return results[:10]

    async def get_download_url(self, md5: str, mirror: str) -> Optional[str]:
        if not md5:
            return None
        for dl in LIBGEN_DL_MIRRORS:
            try:
                url  = f"{dl}{md5}"
                resp = await self._client.get(url, timeout=20)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                # Primary: GET button
                for a in soup.find_all("a", href=True):
                    txt  = a.get_text(strip=True).upper()
                    href = a["href"]
                    if ("GET" in txt or "DOWNLOAD" in txt) and href.startswith("http"):
                        logger.info(f"LibGen: DL URL via {dl}")
                        return href
                # Fallback: link containing md5
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if md5.lower() in href.lower() and href.startswith("http"):
                        return href
            except Exception as e:
                logger.debug(f"LibGen DL {dl}: {e}")
        logger.warning(f"LibGen: no DL URL for md5={md5}")
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
                    return None
                if "html" in resp.headers.get("content-type", "").lower():
                    return None
                cl = int(resp.headers.get("content-length", 0))
                if cl > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None
                chunks, dl = [], 0
                async for chunk in resp.aiter_bytes(65536):
                    dl += len(chunk)
                    if dl > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                data = b"".join(chunks)
                return data if len(data) > 5000 else None
        except Exception as e:
            logger.error(f"LibGen download error: {e}")
            return None
