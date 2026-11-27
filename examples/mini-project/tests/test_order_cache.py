#: Executable evidence for the c4spec constraint `cache-ttl-bound`.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.order_cache import MAX_TTL_SECONDS, OrderCache  # noqa: E402


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class OrderCacheTtlBoundTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.cache = OrderCache(clock=self.clock)

    def test_default_bound_is_300_seconds(self):
        self.assertEqual(MAX_TTL_SECONDS, 300)

    def test_entry_is_served_within_the_bound(self):
        self.cache.put("product-1", {"id": 1})
        self.clock.advance(299)
        self.assertEqual(self.cache.get("product-1"), {"id": 1})

    def test_entry_at_exact_boundary_is_still_served(self):
        # Requirement says "exceeds", so age == 300s is allowed.
        self.cache.put("product-1", {"id": 1})
        self.clock.advance(300)
        self.assertEqual(self.cache.get("product-1"), {"id": 1})

    def test_entry_is_not_served_past_the_bound(self):
        self.cache.put("product-1", {"id": 1})
        self.clock.advance(301)
        self.assertIsNone(self.cache.get("product-1"))

    def test_expired_entry_is_dropped_not_served_later(self):
        self.cache.put("product-1", {"id": 1})
        self.clock.advance(301)
        self.assertIsNone(self.cache.get("product-1"))
        self.assertIsNone(self.cache.get("product-1"))

    def test_ttl_above_the_bound_is_rejected(self):
        with self.assertRaises(ValueError):
            OrderCache(ttl=301, clock=self.clock)


if __name__ == "__main__":
    unittest.main()
