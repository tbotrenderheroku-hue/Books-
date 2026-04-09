"""
Unified book search aggregator.

Source priority on Render free tier:
  1. LibGen       — accessible, no auth needed, best for books
  2. Project Gutenberg — accessible, public domain classics
  3. Open Library  — accessible, good for popular titles
  4. Z-Library     — DNS-blocked on Render free tier (works if accessible)
  5. Anna's Archive — DNS-blocked on Render free tier (stub)

Results are ordered: LibGen first so users see real downloadable files.
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

_zlib = ZLibrarySource()
_libgen = LibgenSource()
_gutenberg = GutenbergSource()
_openlibrary = OpenLibrarySource()
_annas = AnnasArchiveSource()

_book_cache: dict[str, BookResult] = {}


async def search_all_sources(query: str, page: int = 1) -> list[BookResult]:
    """
    Search all sources concurrently.
    LibGen is prioritised (placed first) since it works on Render free tier.
    Z-Library results added if reachable.
    """
    tasks = [
        _libgen.search(query),           # PRIMARY — works on Render
        _gutenberg.search(query),         # works on Render
        _openlibrary.search(query, page=page),  # works on Render
        _zlib.search(query, page=page),   # may be DNS-blocked on Render
        _annas.search(query),             # DNS-blocked on Render — silent stub
    ]

    source_labels = ["Libgen", "Project Gutenberg", "Open Library", "Z-Library", "Anna's Archive"]
    buckets: dict[str, list[BookResult]] = {s: [] for s in source_labels}

    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for label, result in zip(source_labels, gathered):
        if isinstance(result, list):
            for book in result:
                buckets[book.source].append(book)
        elif isinstance(result, Exception):
            logger.warning(f"Source '{label}' error: {result}")

    # Merge in priority order
    all_results: list[BookResult] = []
    for label in source_labels:
        all_results.extend(buckets[label])

    # Deduplicate by title+format
    seen: set[str] = set()
    deduped: list[BookResult] = []
    for book in all_results:
        key = f"{book.title[:40].lower().strip()}_{book.format}"
        if key not in seen:
            seen.add(key)
            deduped.append(book)
            _book_cache[book.book_id] = book

    total = len(deduped)
    logger.info(
        f"Search '{query}' page={page}: {total} results "
        f"(libgen={len(buckets['Libgen'])}, "
        f"gutenberg={len(buckets['Project Gutenberg'])}, "
        f"openlibrary={len(buckets['Open Library'])}, "
        f"zlib={len(buckets['Z-Library'])})"
    )
    return deduped[:15]


def get_cached_book(book_id: str) -> Optional[BookResult]:
    return _book_cache.get(book_id)


async def download_book(book: BookResult) -> Optional[bytes]:
    """Download using the correct source handler."""
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
            mirror = book.extra.get("mirror", "https://libgen.is")
            if not url and md5:
                url = await _libgen.get_download_url(md5, mirror)
            if url:
                return await _libgen.download_file(url)

        elif source == "Anna's Archive":
            return None  # blocked on Render

        elif source == "Project Gutenberg":
            return await _gutenberg.download_file(url)

        elif source == "Open Library":
            return await _openlibrary.download_file(url)

    except Exception as e:
        logger.error(f"Download failed for {book.book_id} ({source}): {e}")

    return None


__all__ = ["search_all_sources", "get_cached_book", "download_book", "BookResult"]
