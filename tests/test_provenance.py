"""Source-bound review integrity: paired provenance, binding and fail-closed paths."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents" / "skills" / "c4spec" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from diff import build_review, compare, load  # noqa: E402
import provenance  # noqa: E402


def git(cwd, *args):
    completed = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if completed.returncode != 0:
        raise AssertionError("git " + " ".join(args) + " failed: " + completed.stderr)
    return completed.stdout.strip()


def version_command(version):
    """A real executable whose own output reports ``version``."""
    return '{} -c "print(\'{}\')"'.format(sys.executable, version)


def export_model(technology="Python"):
    """A small computed-export fixture; real 1.59.4/1.60.0 exports are tested separately."""
    return {"projectId": "demo",
            "elements": {"app": {"id": "app", "kind": "container", "title": "App",
                                 "technology": technology,
                                 "description": {"txt": "Serves requests"}}},
            "relations": {}, "views": {}}


class ModelRepo:
    """A tiny Git repository holding one LikeC4 project plus an out-of-tree export dir."""

    def __init__(self, root):
        self.root = Path(root)
        self.model_dir = self.root / "architecture"
        (self.model_dir / "model").mkdir(parents=True)
        (self.model_dir / "likec4.config.json").write_text('{"name":"demo"}\n', encoding="utf-8")
        self.exports = self.root.with_name(self.root.name + "-exports")
        self.exports.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "C4Spec Test")
        git(self.root, "config", "user.email", "c4spec@example.invalid")

    def write_model(self, comment="alpha", technology="Python"):
        (self.model_dir / "model" / "shop.c4").write_text(
            "specification {\n  element container\n}\n\n"
            "model {\n  // " + comment + "\n"
            "  app = container 'App' {\n    technology '" + technology + "'\n"
            "    description 'Serves requests'\n  }\n}\n", encoding="utf-8")

    def commit(self, message="change"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    def export(self, name, document, duplicate=False):
        path = self.exports / (name + ".json")
        payload = [document, deepcopy(document)] if duplicate else document
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path


class ProvenanceArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = ModelRepo(Path(self.tmp.name) / "repo")
        self.repo.write_model("alpha")
        self.commit = self.repo.commit("alpha")
        self.export = self.repo.export("model", export_model())

    def build(self, **overrides):
        values = {"model_dir": self.repo.model_dir, "export": self.export,
                  "commit": self.commit, "compiler_version": "1.60.0"}
        values.update(overrides)
        return provenance.build_provenance(**values)

    def test_manifest_is_sorted_deterministic_and_covers_config(self):
        document = self.build()
        self.assertEqual([entry["path"] for entry in document["sources"]],
                         ["likec4.config.json", "model/shop.c4"])
        self.assertTrue(document["sourcesDigest"].startswith("sha256:"))
        self.assertTrue(document["gitVerified"])
        self.assertEqual(document["modelDir"], "architecture")
        self.assertEqual(document["export"]["projectId"], "demo")
        self.assertFalse(document["export"]["insideWorkTree"])
        self.assertEqual(document, self.build())

    def test_manifest_digest_is_order_and_content_sensitive(self):
        document = self.build()
        reversed_digest = provenance.manifest_digest(list(reversed(document["sources"])))
        self.assertNotEqual(reversed_digest, document["sourcesDigest"])
        changed = deepcopy(document["sources"])
        changed[0]["sha256"] = "0" * 64
        self.assertNotEqual(provenance.manifest_digest(changed), document["sourcesDigest"])

    def test_rejects_missing_empty_and_configless_directories(self):
        with self.assertRaisesRegex(provenance.InputError, "must exist"):
            self.build(model_dir=self.repo.root / "missing")
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(provenance.InputError, "no .c4"):
            self.build(model_dir=empty)
        configless = Path(self.tmp.name) / "configless"
        configless.mkdir()
        (configless / "model.c4").write_text("model { }\n", encoding="utf-8")
        with self.assertRaisesRegex(provenance.InputError, "no LikeC4 project config"):
            self.build(model_dir=configless)

    def test_rejects_two_project_configs(self):
        (self.repo.model_dir / ".likec4rc").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(provenance.InputError, "multiple LikeC4 project configs"):
            self.build()

    def test_rejects_symlinked_source(self):
        outside = Path(self.tmp.name) / "outside.c4"
        outside.write_text("model { }\n", encoding="utf-8")
        link = self.repo.model_dir / "model" / "linked.c4"
        link.symlink_to(outside)
        with self.assertRaisesRegex(provenance.InputError, "symlinked source"):
            self.build()
        link.unlink()
        outside.unlink()

    def test_rejects_bad_commit_and_version(self):
        for commit in ("1dae31c", "1DAE31C9575FC4D5CF834111D87810F1659EC5ED", "", None):
            with self.subTest(commit=commit):
                with self.assertRaisesRegex(provenance.InputError, "40-character"):
                    self.build(commit=commit)
        with self.assertRaisesRegex(provenance.InputError, "compiler version"):
            self.build(compiler_version="latest")

    def test_rejects_uncommitted_edit_and_accepts_the_right_commit(self):
        self.repo.write_model("alpha", technology="Python 3.12")
        with self.assertRaisesRegex(provenance.InputError, "does not match commit"):
            self.build()
        second = self.repo.commit("technology change")
        document = self.build(commit=second)
        self.assertEqual(document["gitCommit"], second)

    def test_rejects_a_tracked_generated_export(self):
        tracked = self.repo.root / "architecture" / "export.json"
        tracked.write_text(json.dumps(export_model()), encoding="utf-8")
        self.repo.commit("commit an export")
        with self.assertRaisesRegex(provenance.InputError, "must not be committed"):
            self.build(export=tracked)

    def test_flags_an_untracked_export_inside_the_work_tree(self):
        inside = self.repo.root / "architecture" / "scratch-export.json"
        inside.write_text(json.dumps(export_model()), encoding="utf-8")
        document = self.build(export=inside)
        self.assertTrue(document["export"]["insideWorkTree"])

    def test_rejects_ambiguous_export_and_bad_json(self):
        other = deepcopy(export_model())
        other["projectId"] = "other"
        two = self.repo.export("two-projects", [export_model(), other])
        with self.assertRaisesRegex(provenance.InputError, "multiple project IDs"):
            self.build(export=two)
        self.assertEqual(self.build(export=two, project="other")["export"]["projectId"], "other")
        broken = self.repo.exports / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(provenance.InputError, "valid UTF-8 JSON"):
            self.build(export=broken)
        with self.assertRaisesRegex(provenance.InputError, "existing regular file"):
            self.build(export=self.repo.exports / "absent.json")


class ProvenanceValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = ModelRepo(Path(self.tmp.name) / "repo")
        self.repo.write_model("alpha")
        self.commit = self.repo.commit("alpha")
        self.export = self.repo.export("model", export_model())
        self.document = provenance.build_provenance(
            self.repo.model_dir, self.export, self.commit, "1.60.0")

    def tampered(self, mutate):
        document = deepcopy(self.document)
        mutate(document)
        return document

    def test_accepts_a_well_formed_artifact(self):
        provenance.validate_provenance(deepcopy(self.document))

    def test_rejects_unknown_and_missing_fields(self):
        with self.assertRaisesRegex(provenance.InputError, "unknown fields"):
            provenance.validate_provenance(self.tampered(lambda d: d.update({"owner": "someone"})))
        with self.assertRaisesRegex(provenance.InputError, "missing fields"):
            provenance.validate_provenance(self.tampered(lambda d: d.pop("export")))

    def test_rejects_unverified_or_malformed_identity(self):
        with self.assertRaisesRegex(provenance.InputError, "not verified"):
            provenance.validate_provenance(self.tampered(lambda d: d.update({"gitVerified": False})))
        with self.assertRaisesRegex(provenance.InputError, "40-character"):
            provenance.validate_provenance(self.tampered(lambda d: d.update({"gitCommit": self.commit.upper()})))
        with self.assertRaisesRegex(provenance.InputError, "compilerVersion"):
            provenance.validate_provenance(self.tampered(lambda d: d.update({"compilerVersion": "v1"})))
        with self.assertRaisesRegex(provenance.InputError, "schemaVersion"):
            provenance.validate_provenance(self.tampered(lambda d: d.update({"schemaVersion": 2})))
        with self.assertRaisesRegex(provenance.InputError, "compilerCommandReported"):
            provenance.validate_provenance(
                self.tampered(lambda d: d.update({"compilerCommandReported": "yes"})))

    def test_rejects_reordered_duplicated_or_unsafe_sources(self):
        with self.assertRaisesRegex(provenance.InputError, "sorted by path"):
            provenance.validate_provenance(
                self.tampered(lambda d: d.update({"sources": list(reversed(d["sources"]))})))
        with self.assertRaisesRegex(provenance.InputError, "duplicate path"):
            provenance.validate_provenance(
                self.tampered(lambda d: d.update({"sources": [d["sources"][0], d["sources"][0]]})))
        with self.assertRaisesRegex(provenance.InputError, "safe"):
            provenance.validate_provenance(
                self.tampered(lambda d: d["sources"][0].update({"path": "../escape.c4"})))
        with self.assertRaisesRegex(provenance.InputError, "64 lowercase hex"):
            provenance.validate_provenance(
                self.tampered(lambda d: d["sources"][0].update({"sha256": "abc"})))

    def test_rejects_a_manifest_edit_that_keeps_the_digest(self):
        def edited(document):
            document["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(provenance.InputError, "sourcesDigest does not match"):
            provenance.validate_provenance(self.tampered(edited))

    def test_rejects_bad_export_shape(self):
        with self.assertRaisesRegex(provenance.InputError, "export must contain only"):
            provenance.validate_provenance(
                self.tampered(lambda d: d["export"].update({"path": "/tmp/export.json"})))
        with self.assertRaisesRegex(provenance.InputError, "projectIds"):
            provenance.validate_provenance(
                self.tampered(lambda d: d["export"].update({"projectIds": []})))
        with self.assertRaisesRegex(provenance.InputError, "64 lowercase hex"):
            provenance.validate_provenance(
                self.tampered(lambda d: d["export"].update({"sha256": "XY"})))


class SourceBoundReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = ModelRepo(Path(self.tmp.name) / "repo")
        self.repo.write_model("alpha")
        self.c1 = self.repo.commit("alpha")
        self.export1 = self.repo.export("c1", export_model())
        self.p1 = self.provenance_for(self.export1, self.c1)
        self.p1_verified = self.provenance_for(
            self.export1, self.c1, compiler_command=version_command("1.60.0"))
        self.p1_old_compiler = self.provenance_for(self.export1, self.c1, "1.59.4")
        self.duplicated_export = self.repo.export("duplicated", export_model(), duplicate=True)
        self.duplicated_provenance = self.provenance_for(self.duplicated_export, self.c1)

        # Two source-only edits on sibling branches: same model, different bytes.
        git(self.repo.root, "checkout", "-q", "-b", "comment-beta")
        self.repo.write_model("beta")
        self.c2 = self.repo.commit("beta")
        self.export2 = self.repo.export("c2", export_model())
        self.p2 = self.provenance_for(self.export2, self.c2)
        git(self.repo.root, "checkout", "-q", "-b", "comment-gamma", self.c1)
        self.repo.write_model("gamma")
        self.c3 = self.repo.commit("gamma")
        self.export3 = self.repo.export("c3", export_model())
        self.p3 = self.provenance_for(self.export3, self.c3)
        # A real field change.
        git(self.repo.root, "checkout", "-q", "-b", "field-change", self.c1)
        self.repo.write_model("alpha", technology="Python 3.12")
        self.c4 = self.repo.commit("technology")
        self.export4 = self.repo.export("c4", export_model("Python 3.12"))
        self.p4 = self.provenance_for(self.export4, self.c4)
        # A commit that changes no LikeC4 source at all.
        git(self.repo.root, "checkout", "-q", "-b", "docs-only", self.c1)
        (self.repo.root / "README.md").write_text("docs\n", encoding="utf-8")
        self.c5 = self.repo.commit("docs")
        self.export5 = self.repo.export("c5", export_model("Ruby"))
        self.p5 = self.provenance_for(self.export5, self.c5)
        git(self.repo.root, "checkout", "-q", "comment-beta")

    def provenance_for(self, export, commit, version="1.60.0", compiler_command=None):
        document = provenance.build_provenance(self.repo.model_dir, export, commit, version,
                                               compiler_command=compiler_command)
        suffix = "-verified" if compiler_command else ""
        name = ("prov-" + Path(export).stem + "-" + version.replace(".", "_") + "-"
                + commit[:7] + suffix + ".json")
        path = self.repo.exports / name
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def review(self, base_prov, head_prov, base_export, head_export, change=None, repo_root=None,
               base_ref=None, head_ref=None):
        return build_review(argparse.Namespace(
            base_provenance=str(base_prov), head_provenance=str(head_prov),
            base_ref=base_ref, head_ref=head_ref,
            change=str(change) if change else None,
            repo_root=str(repo_root) if repo_root else None,
            base=str(base_export), head=str(head_export)))

    def test_unbound_comparison_stays_exploratory(self):
        report = compare(load(self.export1), load(self.export2))
        self.assertEqual(report["reviewStatus"], "exploratory")
        self.assertIsNone(report["reviewFingerprint"])
        self.assertIsNone(report["reviewBinding"])
        self.assertFalse(report["humanApprovalVerified"])
        self.assertTrue(report["fingerprint"].startswith("sha256:"))

    def test_source_only_change_changes_review_fingerprint_not_model_fingerprint(self):
        beta = compare(load(self.export1), load(self.export2),
                       self.review(self.p1, self.p2, self.export1, self.export2))
        gamma = compare(load(self.export1), load(self.export3),
                        self.review(self.p1, self.p3, self.export1, self.export3))
        self.assertEqual(beta["elements"]["modified"], [])
        self.assertEqual(gamma["elements"]["modified"], [])
        self.assertEqual(beta["reviewStatus"], "source-bound-self-declared")
        self.assertFalse(beta["reviewAssurance"]["gitBlobsReverified"])
        self.assertFalse(beta["reviewAssurance"]["compilerVersionCommandReported"])
        self.assertFalse(beta["reviewAssurance"]["humanApprovalVerified"])
        self.assertEqual(beta["fingerprint"], gamma["fingerprint"], "model-only fingerprint must be preserved")
        self.assertNotEqual(beta["reviewFingerprint"], gamma["reviewFingerprint"],
                            "comment-only source edits must alter the review fingerprint")
        self.assertFalse(beta["humanApprovalVerified"])

    def test_bound_fingerprint_is_deterministic_and_keeps_the_model_fingerprint(self):
        first = compare(load(self.export1), load(self.export2),
                        self.review(self.p1, self.p2, self.export1, self.export2))
        second = compare(load(self.export1), load(self.export2),
                         self.review(self.p1, self.p2, self.export1, self.export2))
        self.assertEqual(first["reviewFingerprint"], second["reviewFingerprint"])
        self.assertEqual(first["fingerprint"],
                         compare(load(self.export1), load(self.export2))["fingerprint"])

    def test_change_record_only_change_alters_the_review_fingerprint(self):
        first = self.repo.exports / "change-a.json"
        second = self.repo.exports / "change-b.json"
        first.write_text(json.dumps({"schemaVersion": 1, "id": "demo-change",
                                     "intent": "first intent", "scope": ["app"]}), encoding="utf-8")
        second.write_text(json.dumps({"schemaVersion": 1, "id": "demo-change",
                                      "intent": "second intent", "scope": ["app"]}), encoding="utf-8")
        a = compare(load(self.export1), load(self.export2),
                    self.review(self.p1, self.p2, self.export1, self.export2, change=first))
        b = compare(load(self.export1), load(self.export2),
                    self.review(self.p1, self.p2, self.export1, self.export2, change=second))
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["reviewFingerprint"], b["reviewFingerprint"])
        self.assertEqual(a["reviewBinding"]["change"]["id"], "demo-change")
        self.assertNotEqual(a["reviewBinding"]["change"]["sha256"], b["reviewBinding"]["change"]["sha256"])

    def test_field_change_is_reported_and_bound_to_both_manifests(self):
        report = compare(load(self.export1), load(self.export4),
                         self.review(self.p1, self.p4, self.export1, self.export4))
        self.assertEqual(report["elements"]["modified"], ["app"])
        self.assertEqual(report["elements"]["fieldChanges"]["app"]["technology"]["after"], "Python 3.12")
        base = report["reviewBinding"]["base"]
        head = report["reviewBinding"]["head"]
        self.assertNotEqual(base["sourcesDigest"], head["sourcesDigest"])
        self.assertEqual(base["compilerVersion"], "1.60.0")
        self.assertEqual(base["gitCommit"], self.c1)
        self.assertEqual(head["gitCommit"], self.c4)
        self.assertTrue(report["reviewFingerprint"].startswith("sha256:"))

    def test_stale_or_altered_export_fails_closed(self):
        self.export2.write_text(json.dumps(export_model(), indent=4) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "do not match its provenance digest"):
            compare(load(self.export1), load(self.export2),
                    self.review(self.p1, self.p2, self.export1, self.export2))

    def test_partial_pair_and_bare_refs_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "BOTH --base-provenance"):
            build_review(argparse.Namespace(base_provenance=str(self.p1), head_provenance=None,
                                            base_ref=None, head_ref=None, change=None,
                                            repo_root=None, base=str(self.export1), head=str(self.export2)))
        with self.assertRaisesRegex(ValueError, "require paired provenance"):
            build_review(argparse.Namespace(base_provenance=None, head_provenance=None,
                                            base_ref=self.c1, head_ref=None, change=None,
                                            repo_root=None, base=str(self.export1), head=str(self.export2)))

    def test_wrong_ref_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match its provenance commit"):
            self.review(self.p1, self.p2, self.export1, self.export2, base_ref=self.c2)
        with self.assertRaisesRegex(ValueError, "40-character"):
            self.review(self.p1, self.p2, self.export1, self.export2, base_ref="deadbeef")

    def test_same_commit_on_both_sides_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "two different Git commits"):
            compare(load(self.export1), load(self.export1),
                    self.review(self.p1, self.p1, self.export1, self.export1))

    def test_changed_model_without_source_evidence_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no source evidence"):
            compare(load(self.export1), load(self.export5),
                    self.review(self.p1, self.p5, self.export1, self.export5))

    def test_repo_root_reverification_catches_a_forged_manifest(self):
        forged = json.loads(self.p1.read_text(encoding="utf-8"))
        forged["sources"][1]["sha256"] = "0" * 64
        forged["sourcesDigest"] = provenance.manifest_digest(forged["sources"])
        forged_path = self.repo.exports / "forged-provenance.json"
        forged_path.write_text(json.dumps(forged), encoding="utf-8")
        # Without the repository the artifact is only internally consistent.
        unchecked = compare(load(self.export1), load(self.export2),
                            self.review(forged_path, self.p2, self.export1, self.export2))
        self.assertTrue(any("re-verification skipped" in text
                            for text in unchecked["reviewLimitations"]))
        with self.assertRaisesRegex(provenance.InputError, "does not match commit"):
            compare(load(self.export1), load(self.export2),
                    self.review(forged_path, self.p2, self.export1, self.export2,
                                repo_root=self.repo.root))

    def test_repo_root_reverification_accepts_honest_provenance(self):
        report = compare(load(self.export1), load(self.export4),
                         self.review(self.p1, self.p4, self.export1, self.export4,
                                     repo_root=self.repo.root))
        self.assertIn("source manifests re-enumerated and re-verified against the named Git commits",
                      report["reviewBinding"]["checks"])
        self.assertEqual(report["reviewStatus"], "source-bound-reverified")
        self.assertTrue(report["reviewAssurance"]["gitBlobsReverified"])
        self.assertEqual(report["reviewAssurance"]["level"], "git-verified")
        self.assertEqual(report["elements"]["modified"], ["app"])

    def test_compiler_version_is_bound_into_the_fingerprint(self):
        a = compare(load(self.export1), load(self.export2),
                    self.review(self.p1_old_compiler, self.p2, self.export1, self.export2))
        b = compare(load(self.export1), load(self.export2),
                    self.review(self.p1, self.p2, self.export1, self.export2))
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["reviewFingerprint"], b["reviewFingerprint"])

    def test_duplicate_project_array_export_binds_normally(self):
        report = compare(load(self.duplicated_export), load(self.export2),
                         self.review(self.duplicated_provenance, self.p2,
                                     self.duplicated_export, self.export2))
        self.assertEqual(report["reviewStatus"], "source-bound-self-declared")
        self.assertEqual(report["reviewBinding"]["base"]["export"]["projectIds"], ["demo"])
        self.assertEqual(report["elements"]["modified"], [])

    def test_compiler_version_is_verified_only_by_running_the_command(self):
        command = version_command("1.60.0")
        verified = self.provenance_for(self.export2, self.c2, compiler_command=command)
        self.assertTrue(json.loads(verified.read_text(encoding="utf-8"))["compilerCommandReported"])
        report = compare(load(self.export1), load(self.export2),
                         self.review(self.p1_verified, verified, self.export1, self.export2,
                                     repo_root=self.repo.root))
        self.assertEqual(report["reviewAssurance"]["level"], "git-verified-compiler-reported")
        self.assertTrue(report["reviewAssurance"]["compilerVersionCommandReported"])
        declared_only = compare(load(self.export1), load(self.export2),
                                self.review(self.p1, self.p2, self.export1, self.export2,
                                            repo_root=self.repo.root))
        self.assertEqual(declared_only["reviewAssurance"]["level"], "git-verified")
        self.assertFalse(declared_only["reviewAssurance"]["compilerVersionCommandReported"])
        self.assertTrue(any("caller-supplied" in text for text in declared_only["reviewLimitations"]))

    def test_compiler_command_must_actually_report_the_version(self):
        with self.assertRaisesRegex(provenance.InputError, "does not report"):
            self.provenance_for(self.export2, self.c2, "1.60.0",
                                compiler_command=version_command("1.59.4"))
        with self.assertRaisesRegex(provenance.InputError, "could not be executed"):
            provenance.build_provenance(self.repo.model_dir, self.export2, self.c2, "1.60.0",
                                        compiler_command="/nonexistent-likec4 --version")

    def test_forged_command_reported_flag_cannot_claim_exporter_verification(self):
        forged = []
        for source in (self.p1, self.p2):
            document = json.loads(source.read_text(encoding="utf-8"))
            document["compilerCommandReported"] = True
            path = self.repo.exports / ("forged-" + source.stem + ".json")
            path.write_text(json.dumps(document), encoding="utf-8")
            forged.append(path)
        report = compare(load(self.export1), load(self.export2),
                         self.review(forged[0], forged[1], self.export1, self.export2,
                                     repo_root=self.repo.root))
        self.assertEqual(report["reviewAssurance"]["level"], "git-verified-compiler-reported")
        self.assertTrue(report["reviewAssurance"]["compilerVersionCommandReported"])
        self.assertFalse(report["reviewAssurance"]["exportBoundToCompiler"])
        self.assertTrue(any("does not prove which LikeC4 binary" in text
                            for text in report["reviewLimitations"]))
        self.assertFalse(report["humanApprovalVerified"])

    def test_manifest_omission_and_foreign_entry_are_caught_by_git(self):
        omitted_doc = json.loads(self.p2.read_text(encoding="utf-8"))
        omitted_doc["sources"] = [entry for entry in omitted_doc["sources"]
                                  if not entry["path"].endswith("shop.c4")]
        omitted_doc["sourcesDigest"] = provenance.manifest_digest(omitted_doc["sources"])
        omitted = self.repo.exports / "omitted-manifest.json"
        omitted.write_text(json.dumps(omitted_doc), encoding="utf-8")
        unchecked = compare(load(self.export1), load(self.export2),
                            self.review(self.p1, omitted, self.export1, self.export2))
        self.assertEqual(unchecked["reviewStatus"], "source-bound-self-declared")
        self.assertTrue(any("self-declared by the sidecars" in text
                            for text in unchecked["reviewLimitations"]))
        with self.assertRaisesRegex(provenance.InputError, "omits sources committed"):
            compare(load(self.export1), load(self.export2),
                    self.review(self.p1, omitted, self.export1, self.export2,
                                repo_root=self.repo.root))

        foreign_doc = json.loads(self.p2.read_text(encoding="utf-8"))
        foreign_doc["sources"] = sorted(foreign_doc["sources"]
                                        + [{"path": "model/ghost.c4", "sha256": "0" * 64}],
                                        key=lambda entry: entry["path"])
        foreign_doc["sourcesDigest"] = provenance.manifest_digest(foreign_doc["sources"])
        foreign = self.repo.exports / "foreign-manifest.json"
        foreign.write_text(json.dumps(foreign_doc), encoding="utf-8")
        with self.assertRaisesRegex(provenance.InputError, "absent from commit"):
            compare(load(self.export1), load(self.export2),
                    self.review(self.p1, foreign, self.export1, self.export2,
                                repo_root=self.repo.root))

    def test_cli_end_to_end_and_fail_closed_exit_code(self):
        provenance_path = self.repo.exports / "cli-provenance.json"
        built = subprocess.run(
            [sys.executable, str(SCRIPTS / "provenance.py"),
             "--model-dir", str(self.repo.model_dir), "--export", str(self.export2),
             "--git-commit", self.c2, "--compiler-version", "1.60.0", "--out", str(provenance_path)],
            capture_output=True, text=True, check=False)
        self.assertEqual(built.returncode, 0, built.stderr)
        verified = subprocess.run(
            [sys.executable, str(SCRIPTS / "diff.py"),
             "--base", str(self.export2), "--head", str(self.export4),
             "--base-provenance", str(provenance_path), "--head-provenance", str(self.p4),
             "--base-ref", self.c2, "--head-ref", self.c4, "--repo-root", str(self.repo.root)],
            capture_output=True, text=True, check=False)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        report = json.loads(verified.stdout)
        self.assertEqual(report["reviewStatus"], "source-bound-reverified")
        self.assertTrue(report["reviewFingerprint"].startswith("sha256:"))
        self.export4.write_text(json.dumps(export_model("Python 3.12"), indent=8), encoding="utf-8")
        replayed = subprocess.run(
            [sys.executable, str(SCRIPTS / "diff.py"),
             "--base", str(self.export2), "--head", str(self.export4),
             "--base-provenance", str(provenance_path), "--head-provenance", str(self.p4)],
            capture_output=True, text=True, check=False)
        self.assertEqual(replayed.returncode, 2)
        self.assertIn("do not match its provenance digest", replayed.stderr)


if __name__ == "__main__":
    unittest.main()
