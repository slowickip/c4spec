"""Prove PR comment behavior with LikeC4 diagrams from real Git revisions."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
COMPILER = ROOT / "node_modules/.bin/likec4"
sys.path.insert(0, str(SCRIPTS))
from pr_model_diff import MARKER, MAX_COMMENT_BYTES, mermaid_block, render_comment, write_png_inputs

MODEL = """specification {
  element system
}
model {
  app = system 'Application'
}
views {
  view index {
    title 'System context'
    include *
  }
}
"""
ADDITIONS = """  support = system 'Support'
  app -> support 'Requests help'
"""
PROPOSAL = """diff addSupport 'Add support' {
  add {
    support = system 'Support'
    app -> support 'Requests help'
  }
}
"""


class CommentFormattingTests(unittest.TestCase):
    def test_empty_comparison_creates_no_comment(self):
        self.assertEqual(self.render([]), ("", ""))

    def test_visual_comment_links_to_rendered_fallback(self):
        block = mermaid_block("graph TD\n  a --> b")
        comment, full = self.render([block])
        self.assertIn("[Download rendered diagrams](https://github.com/owner/repo/actions/runs/100#artifacts)", comment)
        self.assertIn(block, comment)
        self.assertIn(block, full)

    def test_oversized_comparison_keeps_complete_diagrams_only(self):
        large = mermaid_block("graph TD\n" + "x" * MAX_COMMENT_BYTES)
        small = mermaid_block("graph TD\n  a --> b")
        comment, full = self.render([large, small])
        self.assertLessEqual(len(comment.encode("utf-8")), MAX_COMMENT_BYTES)
        self.assertIn(small, comment)
        self.assertNotIn(large, comment)
        self.assertIn(large, full)
        self.assertIn(small, full)
        link_only, full = self.render([large])
        self.assertIn("[Download rendered diagrams]", link_only)
        self.assertNotIn("```mermaid", link_only)
        self.assertIn(large, full)

    def test_mermaid_fence_cannot_be_closed_by_an_embedded_fence(self):
        self.assertEqual(mermaid_block("graph TD\n```\n@user"), "````mermaid\ngraph TD\n```\n@user\n````\n")

    def test_download_index_preserves_diagram_order_and_long_fences(self):
        first = 'graph TD\n  a["backticks"]\n  %% ````'
        second = 'graph TD\n  b --> c'
        _, full = self.render(["**First**\n\n" + mermaid_block(first), "**Second**\n\n" + mermaid_block(second)])
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch)
            write_png_inputs(full, output)
            self.assertEqual((output / "diagram-names.txt").read_text(), "diagram-1\ndiagram-2\n")
            self.assertEqual((output / "diagram-1.mmd").read_text(), first + "\n")
            self.assertEqual((output / "diagram-2.mmd").read_text(), second + "\n")
            index = (output / "diagrams.md").read_text()
            self.assertIn("**First**\n\n![Diagram 1](./diagram-1.png)", index)
            self.assertIn("**Second**\n\n![Diagram 2](./diagram-2.png)", index)
            self.assertNotIn("mermaid", index)

    def render(self, blocks):
        return render_comment(blocks, repo="owner/repo", run_id=100,
                              merge_base="a" * 40, head="b" * 40)


@unittest.skipUnless(COMPILER.exists(), "Run npm ci to exercise the pinned LikeC4 compiler")
class PullRequestModelDiffTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "user.name", "C4Spec tests")
        self.git("commit", "--allow-empty", "-qm", "empty", "--no-gpg-sign")
        self.empty = self.git("rev-parse", "HEAD")
        self.model = self.repo / "architecture/system.c4"
        self.model.parent.mkdir()
        self.model.write_text(MODEL)
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "test change", "--no-gpg-sign")
        return self.git("rev-parse", "HEAD")

    def generate(self, base, head):
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch)
            subprocess.run([
                sys.executable, str(SCRIPTS / "pr_model_diff.py"),
                "--base", base, "--head", head, "--repo", "owner/repo",
                "--pr", "42", "--run-id", "100", "--compiler", str(COMPILER),
                "--out", str(out),
            ], cwd=self.repo, check=True)
            note = (out / "comment.md").read_bytes()
            self.assertEqual(json.loads((out / "metadata.json").read_text()), {
                "base": base, "head": head, "repo": "owner/repo", "pr": 42,
                "runId": 100, "commentBytes": len(note),
            })
            self.assertNotIn(b"diff --git", note)
            self.assertEqual((out / "diagrams.md").exists(), bool(note))
            return note.decode()

    def test_docs_formatting_and_nonvisual_model_changes_are_silent(self):
        (self.repo / "README.md").write_text("# Documentation\n")
        self.assertEqual(self.generate(self.base, self.commit()), "")
        self.model.write_text("// Clarification\n\n" + MODEL.replace("  app", "    app"))
        self.assertEqual(self.generate(self.base, self.commit()), "")
        self.model.write_text(MODEL.replace("app = system 'Application'",
                                           "app = system 'Application' {\n    description 'More detail'\n  }"))
        self.assertEqual(self.generate(self.base, self.commit()), "")

    def test_new_and_removed_views_display_one_diagram_with_colored_outlines(self):
        self.model.write_text(MODEL.replace("model {\n", "model {\n" + ADDITIONS))
        populated = self.commit()
        added = self.generate(self.empty, populated)
        self.assertTrue(added.startswith(MARKER))
        self.assertIn("**Added · System context**", added)
        self.assertEqual(added.count("mermaid\n"), 1)
        self.assertNotIn("Removed", added)
        self.assertNotIn("Before", added)
        self.assertIn('["+ Application"]', added)
        self.assertIn('["+ Support"]', added)
        self.assertIn("fill:#3b82f6,color:#eff6ff,stroke:#3fb950", added)
        self.assertIn("linkStyle 0 stroke:#3fb950", added)
        self.assertNotIn("stroke:#f85149", added)
        self.model.unlink()
        removed = self.generate(populated, self.commit())
        self.assertIn("**Removed · System context**", removed)
        self.assertEqual(removed.count("mermaid\n"), 1)
        self.assertNotIn("Added", removed)
        self.assertNotIn("After", removed)
        self.assertIn('["− Application"]', removed)
        self.assertIn('["− Support"]', removed)
        self.assertIn("fill:#3b82f6,color:#eff6ff,stroke:#f85149,stroke-width:3px,stroke-dasharray:5 3", removed)
        self.assertIn("linkStyle 0 stroke:#f85149,stroke-width:3px,stroke-dasharray:5 3", removed)
        self.assertNotIn("stroke:#3fb950", removed)

    def test_additions_to_an_existing_view_show_green_without_removals(self):
        self.model.write_text(MODEL.replace("model {\n", "model {\n" + ADDITIONS))
        note = self.generate(self.base, self.commit())
        self.assertIn("+ Green outlines show additions", note)
        self.assertIn('["+ Support"]', note)
        self.assertIn('["Application"]', note)
        self.assertNotIn('["+ Application"]', note)
        self.assertIn("fill:#3b82f6,color:#eff6ff,stroke:#2563eb", note)
        self.assertIn("linkStyle 0 stroke:#3fb950", note)
        self.assertNotIn("stroke:#f85149", note)

    def test_view_in_a_nested_source_directory_is_detected(self):
        views = self.model.parent / "views"
        views.mkdir()
        (views / "focused.c4").write_text("""views {
  view focused {
    title 'Application overview'
    include app
  }
}
""")
        note = self.generate(self.base, self.commit())
        self.assertIn("**Added · Application overview**", note)
        self.assertIn('["+ Application"]', note)
        self.assertEqual(note.count("```mermaid\n"), 1)

    def test_mixed_change_retains_each_nodes_likec4_fill(self):
        self.model.write_text(MODEL.replace("model {\n", "model {\n" + ADDITIONS))
        old = self.commit()
        extra = """  reviewer = system 'Reviewer' {
    style { color amber }
  }
  app -> reviewer 'Requests help'
"""
        self.model.write_text(MODEL.replace("model {\n", "model {\n" + extra))
        note = self.generate(old, self.commit())
        self.assertEqual(note.count("mermaid\n"), 1)
        self.assertRegex(note, r'(n\d+)\["\+ Reviewer"\][\s\S]+style \1 fill:#A35829,color:#FFE0C2,stroke:#3fb950')
        self.assertRegex(note, r'(n\d+)\["− Support"\][\s\S]+style \1 fill:#3b82f6,color:#eff6ff,stroke:#f85149')
        self.assertIn('|"+ Requests help"|', note)
        self.assertIn('|"− Requests help"|', note)

    def test_relationship_label_edit_uses_one_red_green_diagram(self):
        baseline = MODEL.replace("model {\n", "model {\n" + ADDITIONS)
        self.model.write_text(baseline)
        base = self.commit()
        self.model.write_text(baseline.replace("Requests help", "Routes support requests").replace(
            "app = system 'Application'", "app = system 'Application' {\n    description 'Updated details'\n  }",
        ))
        note = self.generate(base, self.commit())
        self.assertEqual(note.count("```mermaid\n"), 1)
        self.assertEqual(note.count('["Application"]'), 1)
        self.assertEqual(note.count('["Support"]'), 1)
        self.assertIn('|"− Requests help"|', note)
        self.assertIn('|"+ Routes support requests"|', note)
        self.assertIn("linkStyle 0 stroke:#f85149,stroke-width:3px,stroke-dasharray:5 3", note)
        self.assertIn("linkStyle 1 stroke:#3fb950", note)

    def test_label_and_style_edit_keeps_both_snapshot_styles(self):
        baseline = MODEL.replace("model {\n", "model {\n" + ADDITIONS)
        self.model.write_text(baseline)
        base = self.commit()
        self.model.write_text(baseline.replace(
            "'Requests help'", "'Routes support requests' { style { color red } }",
        ))
        note = self.generate(base, self.commit())
        self.assertEqual(note.count("```mermaid\n"), 2)
        self.assertIn("Before", note)
        self.assertIn("After", note)

    def test_merge_base_and_net_revert(self):
        self.git("switch", "-qc", "topic")
        self.model.write_text(MODEL.replace("'Application'", "'Storefront'"))
        head = self.commit()
        self.git("switch", "-q", "main")
        self.model.write_text(MODEL.replace("'Application'", "'Main only'"))
        base_tip = self.commit()
        note = self.generate(base_tip, head)
        self.assertIn(f"Merge base: `{self.base}`", note)
        for label in ("Before", "After", "Application", "Storefront"):
            self.assertIn(label, note)
        self.assertNotIn("Main only", note)
        self.git("switch", "-q", "topic")
        self.model.write_text(MODEL)
        self.assertEqual(self.generate(base_tip, self.commit()), "")

    def test_native_proposal_has_a_visual_diff_before_apply(self):
        self.model.write_text(MODEL + PROPOSAL)
        head = self.commit()
        note = self.generate(self.base, head)
        self.assertIn("Proposal addSupport", note)
        self.assertIn('["+ Support"]', note)
        self.assertIn("stroke:#3fb950", note)
        self.assertNotIn("stroke:#f85149", note)
        self.assertEqual(self.model.read_text(), MODEL + PROPOSAL)
        self.assertEqual(self.git("status", "--porcelain"), "")
