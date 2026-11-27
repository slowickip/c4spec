"""Contract tests independent of the network/LikeC4 binary."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("rehearse.py")
SPEC = importlib.util.spec_from_file_location("native_diff_rehearse", MODULE)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class NativeDiffProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = runner.SOURCE.read_text(encoding="utf-8")

    def test_one_authoritative_graph_remains_unchanged(self) -> None:
        updated = runner.proposal_source(self.original)
        self.assertEqual(self.original.count("worker = container 'Notification Worker'"), 1)
        self.assertEqual(updated.count("worker = container 'Notification Worker'"), 1)
        self.assertEqual(updated.count("workerV2 = container 'Notification Worker V2'"), 1)
        self.assertEqual(updated.count("diff replaceNotifications"), 1)
        self.assertTrue(updated.startswith(self.original.split("views {")[0]))

    def test_views_reference_proposed_node_without_renaming_view_id(self) -> None:
        updated = runner.proposal_source(self.original)
        self.assertIn("view shop-overview {", updated)
        self.assertIn("view notifications {", updated)
        self.assertIn(
            "include customer, shop.api, shop.db, shop.broker, shop.worker, shop.workerV2",
            updated,
        )
        self.assertIn(
            "include customer, shop.api, shop.broker, shop.worker, shop.workerV2",
            updated,
        )

    def test_fails_closed_when_view_predicate_is_missing(self) -> None:
        altered = self.original.replace(
            "include customer, shop.api, shop.db, shop.broker, shop.worker",
            "include shop.api, shop.db",
        )
        with self.assertRaisesRegex(ValueError, "Expected exactly one"):
            runner.proposal_source(altered)

    def test_does_not_duplicate_existing_diff(self) -> None:
        with self.assertRaisesRegex(ValueError, "Demo diff unexpectedly exists"):
            runner.proposal_source(self.original + "\ndiff replaceNotifications {}\n")

    def test_syntax_contains_both_remove_and_add(self) -> None:
        self.assertIn("remove {\n    shop.worker", runner.DIFF)
        self.assertIn("add {\n    extend shop", runner.DIFF)
        self.assertNotIn("c4spec/changes/", runner.DIFF)


if __name__ == "__main__":
    unittest.main()
