"""
Anna's Archive — meta-search aggregator across multiple book libraries.
"""

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import ENABLE_ANNAS, MAX_FILE_SIZE_MB
from .zlibrary_source import BookResult

logger = logging.getLogger(__name__)

ANNAS_DOMAINS = [
    "https://annas-archive.org",
    "https://annas-archive.se",
    "https://annas-archive.li",
]


class AnnasArchiveSource:
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BookBot/1.0)",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=30,
        )

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

    async def search(self, query: str) -> list[BookResult]:
        if not ENABLE_ANNAS:
            return []

        for domain in ANNAS_DOMAINS:
            try:
                resp = await self._client.get(
                    f"{domain}/search",
                    params={"q": query, "lang": "en", "content": "book_fiction,book_unknown,book_nonfiction"},
                    timeout=25,
                )
                soup = BeautifulSoup(resp.text, "lxml")
                results = []

                for item in soup.select("a[href^='/md5/']")[:12]:
                    try:
                        md5 = item["href"].replace("/md5/", "").strip("/")
                        title_el = item.select_one(".text-xl, h3, .font-bold")
                        title = title_el.get_text(strip=True) if title_el else "Unknown"

                        meta_els = item.select(".text-sm, .text-gray-500, .italic")
                        author = ""
                        ext = "pdf"
                        size_str = "Unknown"
                        size_bytes = 0

                        full_text = item.get_text(" ", strip=True)
                        parts = full_text.split("·")
                        for part in parts:
                            part = part.strip()
                            if any(e in part.lower() for e in ["pdf", "epub", "mobi", "fb2", "djvu"]):
                                for e in ["pdf", "epub", "mobi", "fb2", "djvu", "azw3"]:
                                    if e in part.lower():
                                        ext = e
                                        break
                            if any(u in part.upper() for u in ["KB", "MB", "GB"]):
                                size_str = part
                                size_bytes = self._parse_size(part)

                        if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                            continue

                        results.append(BookResult(
                            title=title[:120],
                            author=author or "Unknown",
                            language="English",
                            format=ext,
                            size_str=size_str,
                            size_bytes=size_bytes,
                            book_id=f"annas_{md5}",
                            download_url=f"{domain}/md5/{md5}",
                            source="Anna's Archive",
                            extra={"md5": md5, "domain": domain},
                        ))
                    except Exception:
                        continue

                if results:
                    return results[:8]

            except Exception as e:
                logger.warning(f"Anna's Archive search failed on {domain}: {e}")
                continue

        return []

    async def get_download_url(self, md5: str, domain: str) -> Optional[str]:
        """Parse Anna's Archive book page to find a direct download link."""
        try:
            resp = await self._client.get(f"{domain}/md5/{md5}", timeout=20)
            soup = BeautifulSoup(resp.text, "lxml")

            # Look for direct download links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(ext in href.lower() for ext in [".pdf", ".epub", ".mobi"]):
                    if href.startswith("http"):
                        return href
                    return f"{domain}{href}"

            # Libgen slow download fallback
            for a in soup.find_all("a", href=True):
                if "libgen" in a["href"] or "library.lol" in a["href"]:
                    return a["href"]
        except Exception as e:
            logger.warning(f"Anna's get_download_url error: {e}")
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
            logger.error(f"Anna's download error: {e}")
            return None
