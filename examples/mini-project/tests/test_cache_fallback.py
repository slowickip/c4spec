#: Executable evidence for the c4spec constraint `cache-fallback` (change add-cache).
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.product_reads import (  # noqa: E402
    InMemoryProductDb,
    ProductNotFound,
    ProductReads,
)

ROWS = {"p-1": {"id": "p-1", "name": "Desk"}, "p-2": {"id": "p-2", "name": "Lamp"}}


class FakeCache:
    """Cache double: serves values, misses, or fails on demand."""

    def __init__(self, rows=None, failure=None):
        self.rows = dict(rows or {})
        self.failure = failure
        self.calls = 0

    def get(self, product_id):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.rows.get(product_id)


class CacheFallbackTests(unittest.TestCase):
    def setUp(self):
        self.db = InMemoryProductDb(ROWS)

    def test_cache_hit_is_served_without_touching_the_database(self):
        cache = FakeCache(rows={"p-1": {"id": "p-1", "name": "Desk"}})
        row = ProductReads(cache, self.db).read("p-1")
        self.assertEqual(row["name"], "Desk")
        self.assertEqual(self.db.reads, 0, "a cache hit must not query the database")
        self.assertEqual(cache.calls, 1)

    def test_cache_miss_reads_the_database(self):
        cache = FakeCache()
        row = ProductReads(cache, self.db).read("p-2")
        self.assertEqual(row["name"], "Lamp")
        self.assertEqual(self.db.reads, 1)

    def test_cache_outage_falls_back_to_the_database(self):
        cache = FakeCache(failure=RuntimeError("cache connection lost"))
        row = ProductReads(cache, self.db).read("p-1")
        self.assertEqual(row["name"], "Desk")
        self.assertEqual(self.db.reads, 1, "reads must still reach the database")

    def test_cache_timeout_falls_back_to_the_database(self):
        cache = FakeCache(failure=TimeoutError("cache read timed out"))
        self.assertEqual(ProductReads(cache, self.db).read("p-2")["name"], "Lamp")
        self.assertEqual(self.db.reads, 1)

    def test_cache_os_error_falls_back_to_the_database(self):
        cache = FakeCache(failure=OSError("socket closed"))
        self.assertEqual(ProductReads(cache, self.db).read("p-1")["name"], "Desk")

    def test_database_failure_is_not_masked(self):
        class BrokenDb(InMemoryProductDb):
            def get(self, product_id):
                raise ConnectionError("database unavailable")

        cache = FakeCache(failure=RuntimeError("cache down"))
        with self.assertRaises(ConnectionError):
            ProductReads(cache, BrokenDb({})).read("p-1")

    def test_unknown_product_is_reported_not_silently_empty(self):
        with self.assertRaises(ProductNotFound):
            ProductReads(FakeCache(failure=RuntimeError("cache down")), self.db).read("p-404")

    def test_fallback_returns_a_copy_not_shared_state(self):
        cache = FakeCache(failure=RuntimeError("cache down"))
        reads = ProductReads(cache, self.db)
        first = reads.read("p-1")
        first["name"] = "Mutated"
        self.assertEqual(reads.read("p-1")["name"], "Desk")


if __name__ == "__main__":
    unittest.main()
