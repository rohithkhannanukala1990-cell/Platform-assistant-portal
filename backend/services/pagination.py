"""Shared list pagination defaults for large collection endpoints."""

from __future__ import annotations

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def clamp_page(
    page: int | None = None,
    page_size: int | None = None,
    *,
    default_size: int = DEFAULT_PAGE_SIZE,
    max_size: int = MAX_PAGE_SIZE,
) -> tuple[int, int, int]:
    """Return ``(page, page_size, offset)`` with sane bounds."""
    p = max(1, int(page or DEFAULT_PAGE))
    size = max(1, min(int(page_size if page_size is not None else default_size), max_size))
    return p, size, (p - 1) * size
