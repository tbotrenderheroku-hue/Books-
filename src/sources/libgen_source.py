"""
LibGen source — PRIMARY source on Render (LibGen is accessible from Render free tier).
Searches libgen.is, libgen.li, libgen.st as mirrors.
Improved: better scraping, more formats, direct download link extraction.
"""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import MAX_FILE_SIZE_MB, ENABLE_LIBGEN
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

# Mirror order — libgen.is usually most reliable from Render
LIBGEN_SEARCH_MIRRORS = [
    "https://libgen.is",
    "https://libgen.st",
    "https://libgen.li",
    "https://libgen.im",
]

LIBGEN_DOWNLOAD_MIRRORS = [
    "https://library.lol/main/",
    "https://libgen.li/ads.php?md5=",
    "https://libgen.im/ads.php?md5=",
    "https://libgen.st/ads.php?md5=",
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
            },
            follow_redirects=True,
            timeout=30,
        )
        self._working_mirror: Optional[str] = None

    async def _get_mirror(self) -> Optional[str]:
        """Find first reachable search mirror."""
        if self._working_mirror:
            return self._working_mirror
        for mirror in LIBGEN_SEARCH_MIRRORS:
            try:
                r = await self._client.get(f"{mirror}/", timeout=8)
                if r.status_code < 500:
                    self._working_mirror = mirror
                    logger.info(f"LibGen: using mirror {mirror}")
                    return mirror
            except Exception as e:
                logger.debug(f"LibGen mirror {mirror} unreachable: {e}")
                continue
        logger.warning("LibGen: all mirrors unreachable")
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
                timeout=20,
            )

            soup = BeautifulSoup(resp.text, "lxml")

            # libgen.is uses id="search_table", libgen.li uses class="catalog"
            table = (
                soup.find("table", {"id": "search_table"})
                or soup.find("table", {"class": "catalog"})
                or soup.find("table", {"class": "c"})
            )
            if not table:
                logger.warning(f"LibGen: no result table found on {mirror}")
                # Reset mirror so next call re-probes
                self._working_mirror = None
                return []

            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 9:
                    continue
                try:
                    title_tag = cols[2].find("a")
                    title = (title_tag.get_text(strip=True) if title_tag
                             else cols[2].get_text(strip=True))
                    author = cols[1].get_text(strip=True)
                    lang = cols[6].get_text(strip=True) or "English"
                    ext = cols[8].get_text(strip=True).lower().strip(".")
                    size_str = cols[7].get_text(strip=True)

                    if ext not in VALID_FORMATS:
                        continue

                    # Extract MD5
                    md5 = ""
                    if title_tag:
                        href = title_tag.get("href", "")
                        if "md5=" in href.lower():
                            md5 = re.search(r"md5=([a-fA-F0-9]+)", href, re.I)
                            md5 = md5.group(1) if md5 else ""
                        elif "/book/" in href:
                            md5 = href.rstrip("/").split("/")[-1]

                    size_bytes = _parse_size(size_str)
                    if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                        continue

                    results.append(BookResult(
                        title=title[:120],
                        author=author[:80],
                        language=lang,
                        format=ext,
                        size_str=size_str or "Unknown",
                        size_bytes=size_bytes,
                        book_id=f"libgen_{md5 or title[:20].replace(' ', '_')}",
                        download_url="",
                        source="Libgen",
                        extra={"md5": md5, "mirror": mirror},
                    ))
                except Exception as row_err:
                    logger.debug(f"LibGen row parse error: {row_err}")
                    continue

            logger.info(f"LibGen: {len(results)} results for '{query}'")
            return results[:10]

        except Exception as e:
            logger.warning(f"LibGen search failed on {mirror}: {e}")
            self._working_mirror = None
            return []

    async def get_download_url(self, md5: str, mirror: str) -> Optional[str]:
        """Try each download mirror to get a real GET link."""
        if not md5:
            return None

        for dl_mirror in LIBGEN_DOWNLOAD_MIRRORS:
            try:
                url = f"{dl_mirror}{md5}"
                resp = await self._client.get(url, timeout=20)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "lxml")

                # Try "GET" link first
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True).upper()
                    if "GET" in text or "DOWNLOAD" in text:
                        if href.startswith("http"):
                            logger.info(f"LibGen: download URL from {dl_mirror}")
                            return href

                # Fallback: any link containing the md5
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if md5.lower() in href.lower() and href.startswith("http"):
                        return href

            except Exception as e:
                logger.debug(f"LibGen DL mirror {dl_mirror} failed: {e}")
                continue

        logger.warning(f"LibGen: no download URL found for md5={md5}")
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                if resp.status_code != 200:
                    logger.warning(f"LibGen download HTTP {resp.status_code}")
                    return None
                content_length = int(resp.headers.get("content-length", 0))
                if content_length > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None
                chunks, downloaded = [], 0
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                file_bytes = b"".join(chunks)

                # Validate — reject HTML error pages served as files
                if len(file_bytes) < 5000:
                    return None

                return file_bytes
        except Exception as e:
            logger.error(f"LibGen download error: {e}")
            return None
