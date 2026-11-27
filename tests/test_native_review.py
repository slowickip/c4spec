import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/c4spec/scripts"))
import native_review as native


class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "consumer"
        self.model = self.repo / "architecture"
        self.model.mkdir(parents=True)
        self.path = self.model / "model.c4"
        self.path.write_text("model { x = service 'X' y = service 'Y' }\n")
        (self.model / "likec4.config.json").write_text('{"name":"consumer"}')
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.base = self.commit("base")
        self.path.write_text(self.path.read_text() + "diff fix { add { x -> y 'calls' } }\n")
        self.proposal = self.commit("proposal")
        self.out = self.root / "review"
        self.mutate_dry_run = False
        self.invalid = False
        self.patcher = patch.object(native, "run_cli", side_effect=self.compiler)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def compiler(self, cli, cwd, *args):
        path = Path(cwd) / "model.c4"
        if args == ("--version",):
            return "1.61.0\n"
        if args[0] == "validate":
            if self.invalid:
                raise native.InputError("Invalid native diff syntax")
            return '{"valid":true}'
        if args[:2] == ("diff", "list"):
            return json.dumps([{"id": "fix", "added": {"relations": 1}}]
                              if "diff fix" in path.read_text() else [])
        if args[:2] == ("diff", "apply"):
            if "--dry-run" not in args or self.mutate_dry_run:
                path.write_text(path.read_text().replace("diff fix { add { x -> y 'calls' } }",
                                                        "model { x -> y 'calls' }"))
            return "apply preview"
        if args[:2] == ("export", "json"):
            applied = "diff fix" not in path.read_text()
            model = {"projectId": "consumer", "elements": {
                x: {"id": x, "kind": "service", "title": x} for x in ("x", "y")},
                "relations": {"r": {"source": "x", "target": "y", "title": "calls"}}
                if applied else {}, "views": {}}
            Path(args[args.index("-o") + 1]).write_text(json.dumps(model))
            return ""
        if args[0] == "build":
            target = Path(args[args.index("--output") + 1])
            target.mkdir()
            (target / "index.html").write_text("<!doctype html><title>Native viewer fixture</title>")
            return ""
        raise AssertionError(args)

    def review(self):
        return native.review(self.repo, "architecture", "fix", self.base, self.out)

    def test_committed_proposal_packet_binds_sources_and_leaves_checkout_unchanged(self):
        packet = self.review()
        self.assertEqual(packet["proposalCommit"], self.proposal)
        self.assertFalse(packet["humanApprovalVerified"])
        self.assertFalse(packet["testsExecuted"])
        self.assertEqual(self.git("status", "--porcelain"), "")
        delta = json.loads((self.out / "semantic-diff.json").read_text())
        self.assertEqual(len(delta["relationships"]["added"]), 1)
        self.assertIn("diff fix", (self.out / "source.patch").read_text())
        self.assertTrue(native.verify_packet(self.repo, "architecture", self.out / "review.json")["valid"])

    def test_changed_proposal_commit_requires_new_review_even_if_model_unchanged(self):
        self.review()
        (self.repo / "code.py").write_text("# another revision")
        self.commit("advance head")
        with self.assertRaisesRegex(native.InputError, "changed since review"):
            native.verify_packet(self.repo, "architecture", self.out / "review.json")

    def test_uncommitted_model_edit_cannot_be_reviewed_as_committed(self):
        self.path.write_text(self.path.read_text() + "// uncommitted\n")
        with self.assertRaisesRegex(ValueError, "does not match commit"):
            self.review()

    def test_dry_run_mutation_is_rejected(self):
        self.mutate_dry_run = True
        with self.assertRaisesRegex(native.InputError, "Dry-run changed"):
            self.review()
        self.assertIn("diff fix", self.path.read_text())

    def test_validation_failure_is_not_hidden_by_successful_diff_list(self):
        self.invalid = True
        with self.assertRaisesRegex(native.InputError, "Invalid native"):
            self.review()
        self.assertFalse((self.out / "review.json").exists())

    def test_multiple_pending_diffs_require_isolation_or_reconciliation(self):
        def two_diffs(cli, cwd, *args):
            if args[:2] == ("diff", "list"):
                return '[{"id":"fix"},{"id":"other"}]'
            return self.compiler(cli, cwd, *args)

        with patch.object(native, "run_cli", side_effect=two_diffs):
            with self.assertRaisesRegex(native.InputError, "one pending native diff"):
                self.review()
        self.assertFalse((self.out / "review.json").exists())

    def test_applied_commit_must_match_reviewed_result_exactly(self):
        self.review()
        self.path.write_bytes((self.out / "applied/model.c4").read_bytes())
        self.commit("apply reviewed diff")
        result = native.verify_packet(self.repo, "architecture", self.out / "review.json", applied=True)
        self.assertTrue(result["valid"])
        self.path.write_text(self.path.read_text() + "// unexpected model drift\n")
        self.commit("drift")
        with self.assertRaisesRegex(native.InputError, "diverge"):
            native.verify_packet(self.repo, "architecture", self.out / "review.json", applied=True)

    def test_output_cannot_be_inside_consumer_repository(self):
        with self.assertRaisesRegex(native.InputError, "outside"):
            native.review(self.repo, "architecture", "fix", self.base, self.repo / "packet")

    def test_changed_review_manifest_is_rechecked_against_git(self):
        self.review()
        path = self.out / "review.json"
        packet = json.loads(path.read_text())
        packet["sources"][0]["sha256"] = "0" * 64
        packet["sourcesDigest"] = native.manifest_digest(packet["sources"])
        path.write_text(json.dumps(packet))
        with self.assertRaisesRegex(ValueError, "does not match commit"):
            native.verify_packet(self.repo, "architecture", path)

    def test_verification_detects_sources_changed_during_compilation(self):
        self.review()

        def concurrent_edit(cli, cwd, *args):
            result = self.compiler(cli, cwd, *args)
            if args[0] == "validate":
                self.path.write_text(self.path.read_text() + "// concurrent edit\n")
            return result

        with patch.object(native, "run_cli", side_effect=concurrent_edit):
            with self.assertRaisesRegex(native.InputError, "Verification changed"):
                native.verify_packet(self.repo, "architecture", self.out / "review.json")


if __name__ == "__main__":
    unittest.main()
