"""
Unified book search aggregator.

Priority order (Z-Library is PRIMARY):
  1. Z-Library     — primary, uses DoH to bypass Render DNS block
  2. LibGen        — libgen.is, works on Render
  3. Project Gutenberg — public domain
  4. Open Library  — publicly downloadable only (403 items skipped)
  5. Anna's Archive — DNS blocked, silent stub
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

_zlib       = ZLibrarySource()
_libgen     = LibgenSource()
_gutenberg  = GutenbergSource()
_openlibrary = OpenLibrarySource()
_annas      = AnnasArchiveSource()

_book_cache: dict[str, BookResult] = {}


async def search_all_sources(query: str, page: int = 1) -> list[BookResult]:
    """Search all sources concurrently. Z-Library results shown first."""

    tasks = [
        _zlib.search(query, page=page),        # PRIMARY
        _libgen.search(query),
        _gutenberg.search(query),
        _openlibrary.search(query, page=page),
        _annas.search(query),
    ]
    source_order = ["Z-Library", "Libgen", "Project Gutenberg", "Open Library", "Anna's Archive"]
    buckets: dict[str, list[BookResult]] = {s: [] for s in source_order}

    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for label, result in zip(source_order, gathered):
        if isinstance(result, list):
            for book in result:
                buckets[book.source].append(book)
        elif isinstance(result, Exception):
            logger.warning(f"Source '{label}' exception: {result}")

    # Merge: Z-Library first
    all_results: list[BookResult] = []
    for label in source_order:
        all_results.extend(buckets[label])

    seen: set[str] = set()
    deduped: list[BookResult] = []
    for book in all_results:
        key = f"{book.title[:40].lower().strip()}_{book.format}"
        if key not in seen:
            seen.add(key)
            deduped.append(book)
            _book_cache[book.book_id] = book

    counts = {s: len(buckets[s]) for s in source_order}
    logger.info(
        f"Search '{query}' p={page}: {len(deduped)} results | "
        f"zlib={counts['Z-Library']} libgen={counts['Libgen']} "
        f"gutenberg={counts['Project Gutenberg']} openlibrary={counts['Open Library']}"
    )
    return deduped[:15]


def get_cached_book(book_id: str) -> Optional[BookResult]:
    return _book_cache.get(book_id)


async def download_book(book: BookResult) -> Optional[bytes]:
    source = book.source
    url    = book.download_url
    try:
        if source == "Z-Library":
            if not url:
                url = await _zlib.get_download_url(book.book_id, book.extra)
            if url:
                return await _zlib.download_file(url)

        elif source == "Libgen":
            md5    = book.extra.get("md5", "")
            mirror = book.extra.get("mirror", "https://libgen.is")
            if not url and md5:
                url = await _libgen.get_download_url(md5, mirror)
            if url:
                return await _libgen.download_file(url)

        elif source == "Project Gutenberg":
            return await _gutenberg.download_file(url)

        elif source == "Open Library":
            return await _openlibrary.download_file(url)

        elif source == "Anna's Archive":
            return None

    except Exception as e:
        logger.error(f"Download failed {book.book_id} ({source}): {e}")

    return None


__all__ = ["search_all_sources", "get_cached_book", "download_book", "BookResult"]
