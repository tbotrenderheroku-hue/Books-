"""
LibGen source — searches libgen.li and libgen.im
"""

import hashlib
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import MAX_FILE_SIZE_MB, ENABLE_LIBGEN
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

LIBGEN_MIRRORS = [
    "https://libgen.li",
    "https://libgen.im",
]

LIBGEN_DOWNLOAD_MIRRORS = [
    "https://libgen.li/ads.php?md5=",
    "https://libgen.im/ads.php?md5=",
    "https://library.lol/main/",
]


class LibgenSource:
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; BookBot/1.0)"},
            follow_redirects=True,
            timeout=30,
        )

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_LIBGEN:
            return []

        results = []
        for mirror in LIBGEN_MIRRORS:
            try:
                resp = await self._client.get(
                    f"{mirror}/index.php",
                    params={
                        "req": query,
                        "res": 25,
                        "sort": "def",
                        "sortmode": "ASC",
                        "fielname": "def",
                    },
                    timeout=20,
                )
                soup = BeautifulSoup(resp.text, "lxml")
                table = soup.find("table", {"class": "catalog"})
                if not table:
                    continue

                rows = table.find_all("tr")[1:]  # skip header
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) < 9:
                        continue
                    try:
                        title_tag = cols[2].find("a")
                        title = title_tag.get_text(strip=True) if title_tag else cols[2].get_text(strip=True)
                        author = cols[1].get_text(strip=True)
                        lang = cols[6].get_text(strip=True) or "English"
                        ext = cols[8].get_text(strip=True).lower()
                        size_str = cols[7].get_text(strip=True)
                        md5 = ""
                        href = title_tag.get("href", "") if title_tag else ""
                        if "md5=" in href:
                            md5 = href.split("md5=")[-1].split("&")[0]
                        elif "book/" in href:
                            md5 = href.split("/")[-1]

                        size_bytes = self._parse_size(size_str)
                        if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                            continue

                        if ext not in ("pdf", "epub", "mobi", "djvu", "fb2", "azw3"):
                            continue

                        results.append(BookResult(
                            title=title[:120],
                            author=author[:80],
                            language=lang,
                            format=ext,
                            size_str=size_str,
                            size_bytes=size_bytes,
                            book_id=f"libgen_{md5}",
                            download_url="",
                            source="Libgen",
                            extra={"md5": md5, "mirror": mirror},
                        ))
                    except Exception:
                        continue

                if results:
                    return results[:8]

            except Exception as e:
                logger.warning(f"Libgen search failed on {mirror}: {e}")
                continue

        return results

    async def get_download_url(self, md5: str, mirror: str) -> Optional[str]:
        """Try each download mirror to get a working link."""
        for dl_mirror in LIBGEN_DOWNLOAD_MIRRORS:
            try:
                url = f"{dl_mirror}{md5}"
                resp = await self._client.get(url, timeout=20)
                soup = BeautifulSoup(resp.text, "lxml")
                # Find the actual GET link
                link = soup.find("a", string=lambda t: t and "GET" in t)
                if link and link.get("href"):
                    return link["href"]
                # Fallback: first download link
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if md5.lower() in href.lower() or "get.php" in href:
                        return href
            except Exception:
                continue
        return None

    async def download_file(self, url: str) -> Optional[bytes]:
        try:
            async with self._client.stream("GET", url, timeout=120) as resp:
                content_length = int(resp.headers.get("content-length", 0))
                if content_length > MAX_FILE_SIZE_MB * 1024 * 1024:
                    return None
                chunks = []
                downloaded = 0
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_FILE_SIZE_MB * 1024 * 1024:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks)
        except Exception as e:
            logger.error(f"Libgen download error: {e}")
            return None

    @staticmethod
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
