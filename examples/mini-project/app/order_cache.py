"""Reference implementation of the shop.api cache TTL bound.

Fixture only: it exists so the behavioral constraint cache-ttl-bound has an
executable check. It is not a production cache, and nothing in the LikeC4
model, the manifests or a deployment imports it.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Tuple

#: Upper bound on how long a cached product read may be served.
MAX_TTL_SECONDS = 300


class OrderCache:
    """Product read cache that refuses entries older than MAX_TTL_SECONDS."""

    def __init__(
        self,
        ttl: float = MAX_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl > MAX_TTL_SECONDS:
            raise ValueError("ttl exceeds the specified bound of 300 seconds")
        self._ttl = ttl
        self._clock = clock
        self._entries: Dict[str, Tuple[float, Any]] = {}

    def put(self, key: str, value: Any) -> None:
        self._entries[key] = (self._clock() + self._ttl, value)

    def get(self, key: str) -> Optional[Any]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() > expires_at:
            del self._entries[key]
            return None
        return value
