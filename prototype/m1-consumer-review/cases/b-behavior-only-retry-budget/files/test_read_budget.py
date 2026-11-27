import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.product_reads import (  # noqa: E402
    READ_ATTEMPTS_BUDGET,
    BoundedCacheRetry,
    InMemoryProductDb,
    ProductReads,
)


class FlakyCache:
    """Cache that raises until `succeed_on` (1-based), then returns the row."""

    def __init__(self, succeed_on=None, row=None):
        self.succeed_on = succeed_on
        self.row = row
        self.calls = 0

    def get(self, product_id):
        self.calls += 1
        if self.succeed_on is not None and self.calls >= self.succeed_on:
            return dict(self.row) if self.row else None
        raise TimeoutError("cache timeout")


class BoundedRetryTests(unittest.TestCase):
    def setUp(self):
        self.db = InMemoryProductDb({"p1": {"id": "p1", "name": "Kettle"}})

    def test_budget_is_two_attempts(self):
        self.assertEqual(READ_ATTEMPTS_BUDGET, 2)

    def test_exhausted_cache_falls_back_to_exactly_one_database_read(self):
        flaky = FlakyCache()
        retry = BoundedCacheRetry(flaky)
        result = ProductReads(retry, self.db).read("p1")
        self.assertEqual(result["name"], "Kettle")
        self.assertEqual(flaky.calls, READ_ATTEMPTS_BUDGET)
        self.assertEqual(retry.attempts, READ_ATTEMPTS_BUDGET)
        self.assertEqual(self.db.reads, 1)

    def test_second_attempt_hit_never_touches_the_database(self):
        flaky = FlakyCache(succeed_on=2, row={"id": "p1", "name": "Cached Kettle"})
        result = ProductReads(BoundedCacheRetry(flaky), self.db).read("p1")
        self.assertEqual(result["name"], "Cached Kettle")
        self.assertEqual(flaky.calls, 2)
        self.assertEqual(self.db.reads, 0)

    def test_budget_is_not_exceeded_under_repeated_failures(self):
        flaky = FlakyCache()
        retry = BoundedCacheRetry(flaky)
        ProductReads(retry, self.db).read("p1")
        self.assertLessEqual(flaky.calls, READ_ATTEMPTS_BUDGET)


if __name__ == "__main__":
    unittest.main()
