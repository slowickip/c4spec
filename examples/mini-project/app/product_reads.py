"""Reference implementation of the `add-cache` fallback requirement (fixture).

`shop.api` reads products through a cache and MUST still serve reads from the
database when the cache is unavailable. Fixture only: an in-memory store, no
PostgreSQL, no network, no production import. It exists so the durable
constraint `cache-fallback` has executable evidence.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class ProductNotFound(LookupError):
    """Raised when neither the cache nor the database holds the product."""


class InMemoryProductDb:
    """Deterministic stand-in for `shop.db`; counts reads so tests can prove bypass."""

    def __init__(self, rows: Dict[str, Dict[str, Any]]) -> None:
        self._rows = {key: dict(value) for key, value in rows.items()}
        self.reads = 0

    def get(self, product_id: str) -> Optional[Dict[str, Any]]:
        self.reads += 1
        row = self._rows.get(product_id)
        return dict(row) if row is not None else None


class CacheAdapter(Protocol):
    """The only cache surface the read path is allowed to depend on."""

    def get(self, product_id: str) -> Optional[Dict[str, Any]]: ...


class ProductReads:
    """Serve product reads, falling back to the database when the cache fails.

    A cache that raises (outage, timeout, broken socket) is treated as
    unavailable and the read continues against the database. A database failure
    is *not* masked: it propagates to the caller.
    """

    def __init__(self, cache: CacheAdapter, db: InMemoryProductDb) -> None:
        self._cache = cache
        self._db = db

    def read(self, product_id: str) -> Dict[str, Any]:
        try:
            cached = self._cache.get(product_id)
        except (RuntimeError, TimeoutError, OSError):
            # Deliberately broad on the cache side only: availability first.
            cached = None
        if cached is not None:
            return dict(cached)
        row = self._db.get(product_id)
        if row is None:
            raise ProductNotFound(product_id)
        return row
