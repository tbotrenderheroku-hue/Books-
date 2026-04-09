"""
Unified book search aggregator — tries all enabled sources.
Supports pagination via page parameter.
"""

import asyncio
import logging
from typing import Optional

from .zlibrary_source import ZLibrarySource, BookResult
from .libgen_source import LibgenSource
from .gutenberg_source import GutenbergSource
from .openlibrary_source import OpenLibrarySource
from .annas_source import AnnasArchiveSource

logger = logging.getLogger(__name__)

# Global singletons
_zlib = ZLibrarySource()
_libgen = LibgenSource()
_gutenberg = GutenbergSource()
_openlibrary = OpenLibrarySource()
_annas = AnnasArchiveSource()

# In-memory book cache: book_id -> BookResult
_book_cache: dict[str, BookResult] = {}


async def search_all_sources(query: str, page: int = 1) -> list[BookResult]:
    """
    Search all sources concurrently and return combined results.
    Z-Library results are prioritised (placed first).
    """
    # Run all sources in parallel; pass page where supported
    tasks = [
        _zlib.search(query, page=page),
        _libgen.search(query),
        _annas.search(query),
        _gutenberg.search(query),
        _openlibrary.search(query, page=page),
    ]
    all_results: list[BookResult] = []
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    # Gather results — Z-Library first so it shows up at top
    source_order = ["Z-Library", "Libgen", "Anna's Archive", "Project Gutenberg", "Open Library"]
    buckets: dict[str, list[BookResult]] = {s: [] for s in source_order}

    for result in gathered:
        if isinstance(result, list):
            for book in result:
                buckets.get(book.source, buckets["Open Library"]).append(book)
        elif isinstance(result, Exception):
            logger.warning(f"Source error: {result}")

    # Combine: ZLib first, then others
    for source in source_order:
        all_results.extend(buckets[source])

    # Deduplicate by title+format
    seen: set[str] = set()
    deduped: list[BookResult] = []
    for book in all_results:
        key = f"{book.title[:40].lower().strip()}_{book.format}"
        if key not in seen:
            seen.add(key)
            deduped.append(book)
            _book_cache[book.book_id] = book

    return deduped[:15]


def get_cached_book(book_id: str) -> Optional[BookResult]:
    return _book_cache.get(book_id)


async def download_book(book: BookResult) -> Optional[bytes]:
    """Download a book using the appropriate source."""
    source = book.source
    url = book.download_url

    try:
        if source == "Z-Library":
            if not url:
                url = await _zlib.get_download_url(book.book_id, book.extra)
            if url:
                return await _zlib.download_file(url)

        elif source == "Libgen":
            md5 = book.extra.get("md5", "")
            mirror = book.extra.get("mirror", "https://libgen.li")
            if not url and md5:
                url = await _libgen.get_download_url(md5, mirror)
            if url:
                return await _libgen.download_file(url)

        elif source == "Anna's Archive":
            md5 = book.extra.get("md5", "")
            domain = book.extra.get("domain", "https://annas-archive.org")
            if not url and md5:
                url = await _annas.get_download_url(md5, domain)
            if url:
                return await _annas.download_file(url)

        elif source == "Project Gutenberg":
            return await _gutenberg.download_file(url)

        elif source == "Open Library":
            return await _openlibrary.download_file(url)

    except Exception as e:
        logger.error(f"Download failed for {book.book_id}: {e}")

    return None


__all__ = ["search_all_sources", "get_cached_book", "download_book", "BookResult"]
