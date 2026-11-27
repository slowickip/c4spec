"""Small, offline regression tests for source-bound native rehearsal summaries."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("native_review_comment", HERE / "review_comment.py")
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)

SHA = "a" * 40
COUNTS = {
    "projectId": "default", "id": "replaceNotifications",
    "title": "Replace notification worker",
    "description": {"txt": "Retire old worker, introduce v2"},
    "added": {"elements": 1, "relations": 2},
    "removed": {"elements": 1, "relations": 0},
    "modified": {"elements": 0},
    "views": [
        {"id": "index", "title": "Landscape view",
         "nodes": {"added": 0, "removed": 0, "modified": 0},
         "edges": {"added": 0, "removed": 0, "modified": 1}},
        {"id": "notifications", "title": "L2 — Notifications",
         "nodes": {"added": 1, "removed": 1, "modified": 0},
         "edges": {"added": 2, "removed": 2, "modified": 0}},
    ],
}
SUMMARY = {
    "likec4Version": "1.61.0", "diff": "replaceNotifications",
    "validatedProposal": True, "dryRunNonMutating": True,
    "appliedAndValidated": True, "staleRemovalRejected": True,
    "overlappingDiffRejected": True, "modelOnlySourcePreserved": True,
}


class ReviewCommentTests(unittest.TestCase):
    def render(self, *, diffs=None, summary=None, sha=SHA, run_id=42):
        return review.render_comment(
            [COUNTS] if diffs is None else diffs,
            SUMMARY if summary is None else summary,
            repo="example-owner/c4spec", run_id=run_id, sha=sha,
        )

    def test_rendered_comment_links_exact_run_and_commit(self):
        result = self.render()
        self.assertIn(SHA, result)
        self.assertIn("https://github.com/example-owner/c4spec/actions/runs/42#artifacts", result)
        self.assertIn("native-diff-as-is-changes-to-be", result)
        self.assertIn("As-is / Changes / To-be", result)
        self.assertIn("human design approval", result)
        self.assertIn("exercises the pinned compiler", result)
        self.assertIn("Tool commit under test", result)
        self.assertIn("+1 / −1 / ~0", result)
        self.assertIn("+2 / −2 / ~0", result)
        self.assertIn("Landscape view", result)

    def test_refuses_failed_or_unverified_checks(self):
        with self.assertRaisesRegex(ValueError, "Missing positive"):
            self.render(summary={**SUMMARY, "staleRemovalRejected": False})

    def test_refuses_wrong_version_or_id(self):
        with self.assertRaisesRegex(ValueError, "pinned"):
            self.render(summary={**SUMMARY, "likec4Version": "1.60.0"})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render(diffs=[{**COUNTS, "id": "other"}])

    def test_refuses_invalid_identity(self):
        with self.assertRaisesRegex(ValueError, "source"):
            self.render(sha="not-a-sha")
        with self.assertRaisesRegex(ValueError, "source"):
            self.render(run_id=0)

    def test_escapes_markdown_and_github_mentions(self):
        bad = {**COUNTS, "views": [{**COUNTS["views"][1],
            "title": "Hi | `name` @reviewer __TICK__ [unsafe](https://example.org)"}]}
        rendered = self.render(diffs=[bad])
        self.assertIn("\\|", rendered)
        self.assertNotIn("@reviewer", rendered)
        self.assertNotIn("`name`", rendered)
        self.assertNotIn("__TICK__", rendered)
        self.assertNotIn("[unsafe](https://example.org)", rendered)

    def test_rejects_invalid_provider_count(self):
        invalid_view = {**COUNTS["views"][1], "nodes": {"added": -1}}
        with self.assertRaisesRegex(ValueError, "Invalid LikeC4 metric"):
            self.render(diffs=[{**COUNTS, "views": [invalid_view]}])


    def test_inline_overlay_is_spliced_before_the_review_instructions(self):
        block = "**Inline native diff**\n\n```mermaid\nflowchart TB\n  a[\"A\"]\n```"
        rendered = review.render_comment([COUNTS], SUMMARY, repo="example-owner/c4spec",
                                         run_id=42, sha=SHA, inline=block)
        self.assertLess(rendered.index("```mermaid"), rendered.index("**Review:**"))
        self.assertIn('a["A"]', rendered)


if __name__ == "__main__":
    unittest.main()
