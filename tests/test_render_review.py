"""Offline review packet: adapter over existing diff/check JSON plus native PNGs."""
from copy import deepcopy
import base64
import re
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".agents" / "skills" / "c4spec" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_review  # noqa: E402

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def binding(commit="1" * 40):
    return {"gitCommit": commit, "compilerVersion": "1.60.0", "compilerCommandReported": True,
            "modelDir": "architecture", "sources": [], "sourcesDigest": "sha256:" + "c" * 64,
            "export": {"sha256": "e" * 64, "projectId": "consumer-demo", "projectIds": ["consumer-demo"],
                       "insideWorkTree": False}}


def diff_document(**overrides):
    document = {
        "schemaVersion": 1,
        "projectId": "consumer-demo",
        "elements": {"added": [], "removed": [], "modified": [],
                     "fieldChanges": {}, "addedDetails": {}, "removedDetails": {}},
        "relationships": {"added": [], "removed": [], "modified": []},
        "views": {"added": [], "removed": [], "modified": [], "fieldChanges": {}},
        "reviewHints": [],
        "fingerprint": "sha256:" + "a" * 64,
        "fingerprintScope": "normalized base and head computed LikeC4 models",
        "limitations": ["Review raw .c4 Git diff: original view selector rules may not appear in computed exports"],
        "reviewStatus": "source-bound-reverified",
        "reviewFingerprint": "sha256:" + "b" * 64,
        "reviewFingerprintScope": "normalized diff + both source manifests + commits + compiler versions",
        "reviewBinding": {"base": binding("1" * 40), "head": binding("2" * 40),
                          "change": None,
                          "assurance": "git-verified-compiler-reported", "checks": [], "humanApprovalVerified": False},
        "reviewAssurance": {"level": "git-verified-compiler-reported", "gitBlobsReverified": True,
                            "compilerVersionCommandReported": True, "exportBoundToCompiler": False,
                            "exportBytesRehashed": True, "humanApprovalVerified": False},
        "reviewLimitations": ["The review fingerprint binds inputs, not identity"],
        "humanApprovalVerified": False,
    }
    document.update(overrides)
    return document


def check_document(**overrides):
    document = {"schemaVersion": 1, "phase": "proposal", "valid": True, "errors": 0, "warnings": 1,
                "implementationConformanceVerified": False, "runtimeVerified": False,
                "testsExecuted": False, "limitations": ["Structural validation only"],
                "findings": [{"severity": "warning", "code": "planned_path",
                              "location": "change.evidence.1",
                              "message": "Planned evidence path does not yet exist"}]}
    document.update(overrides)
    return document


class PacketCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.png = self.root / "recovery-prerequisites.png"
        self.png.write_bytes(PNG_1X1)

    def write(self, name, document, raw=None):
        path = self.root / name
        path.write_text(raw if raw is not None else json.dumps(document), encoding="utf-8")
        return path

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "render_review.py"), *args],
                              capture_output=True, text=True, check=False)

    def packet(self, diff, check=None, renders=(), extra=()):
        args = ["--diff", str(self.write("diff.json", diff)), "--html", str(self.root / "packet.html")]
        if check is not None:
            args += ["--check", str(self.write("check.json", check))]
        for view in renders:
            args += ["--render", f"{view}={self.png}"]
        return self.run_cli(*args, *extra)


class ViewOnlyDeltaTests(PacketCase):
    def view_only(self):
        diff = diff_document()
        diff["views"]["added"] = ["recovery-prerequisites"]
        return diff

    def test_zero_topology_with_new_view_renders_the_view_not_nothing(self):
        result = self.packet(self.view_only(), renders=["recovery-prerequisites"])
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("No element or relationship changes", page)
        self.assertIn("recovery-prerequisites", page)
        self.assertIn("data:image/png;base64,", page)
        self.assertNotIn("no visual evidence", page)
        self.assertIn("NO APPROVAL RECORDED", page)

    def test_view_only_change_without_render_is_an_explicit_warning(self):
        result = self.packet(self.view_only())
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(any("no native LikeC4 PNG supplied for changed view 'recovery-prerequisites'" in warning
                            for warning in payload["warnings"]))
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("No native LikeC4 PNG was supplied", page)
        self.assertIn("recovery-prerequisites", page)

    def test_uncorrelated_render_is_flagged_but_still_rendered(self):
        result = self.packet(diff_document(), renders=["some-other-view"])
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(any("not correlated with any changed view" in warning for warning in payload["warnings"]))
        self.assertIn("some-other-view", (self.root / "packet.html").read_text(encoding="utf-8"))


class InventoryTests(PacketCase):
    def test_topology_delta_keeps_before_after_values(self):
        diff = diff_document()
        diff["elements"]["added"] = ["shop.broker"]
        diff["elements"]["addedDetails"]["shop.broker"] = {
            "id": "shop.broker", "kind": "container", "title": "Message Broker",
            "technology": "RabbitMQ", "description": {"txt": "Stores events"}}
        diff["elements"]["modified"] = ["platform.target-cilium"]
        diff["elements"]["fieldChanges"] = {"platform.target-cilium": {"technology": {
            "beforePresent": True, "afterPresent": True,
            "before": "Cilium 1.20.2", "after": "Cilium (kube-proxy retained)"}}}
        diff["relationships"]["modified"] = [{
            "identity": {"source": "shop.api", "target": "shop.db", "kind": "sync", "title": "reads"},
            "fieldChanges": {"technology": {"beforePresent": False, "afterPresent": True,
                                           "before": None, "after": "SQL over TLS"}}}]
        result = self.packet(diff)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("shop.broker", page)
        self.assertIn("Message Broker", page)
        self.assertIn("Cilium 1.20.2", page)
        self.assertIn("Cilium (kube-proxy retained)", page)
        self.assertIn("SQL over TLS", page)
        self.assertIn("&lt;absent&gt;", page)
        self.assertIn("2 element change(s), 1 relationship change(s), 0 view change(s)", page)

    def test_review_assurance_and_bound_fingerprint_are_verbatim(self):
        result = self.packet(diff_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        for expected in ("source-bound-reverified", "git-verified-compiler-reported",
                         "exportBoundToCompiler", "false", "sha256:" + "a" * 64,
                         "sha256:" + "b" * 64, "1.60.0"):
            self.assertIn(expected, page)

    def test_unbound_legacy_report_is_labelled_not_upgraded(self):
        diff = diff_document()
        diff.pop("reviewStatus")
        diff.pop("reviewFingerprint")
        diff.pop("reviewFingerprintScope")
        diff.pop("reviewBinding")
        diff.pop("reviewAssurance")
        result = self.packet(diff)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("legacy model-only report", page)
        self.assertNotIn("source-bound-reverified", page)

    def test_structural_check_success_never_implies_executed_tests(self):
        result = self.packet(diff_document(), check=check_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("never executes tests", page)
        self.assertIn("testsExecuted <code>false</code> (self-reported)", page)
        self.assertIn("planned_path", page)

    def test_report_without_check_says_so(self):
        result = self.packet(diff_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No check.py report supplied",
                      (self.root / "packet.html").read_text(encoding="utf-8"))


class HostileAndSafetyTests(PacketCase):
    def test_hostile_text_is_escaped_and_csp_forbids_network_and_scripts(self):
        diff = diff_document()
        diff["elements"]["added"] = ["evil"]
        diff["elements"]["addedDetails"]["evil"] = {
            "id": "evil", "kind": "container",
            "title": "<script>alert(1)</script>",
            "technology": '"><img src=x onerror=alert(2)>',
            "description": {"txt": "javascript:alert(3)"}}
        diff["views"]["added"] = ["x</code><script>alert(4)</script>"]
        result = self.packet(diff)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("javascript:alert", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("default-src 'none'", page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_no_input_overwrite_and_no_architecture_writes(self):
        diff = self.write("diff.json", diff_document())
        overwrite = self.run_cli("--diff", str(diff), "--html", str(diff))
        self.assertEqual(overwrite.returncode, 2)
        self.assertIn("overwrite an input", overwrite.stderr)
        (self.root / "architecture").mkdir()
        guarded = self.run_cli("--diff", str(diff), "--html", str(self.root / "architecture" / "packet.html"))
        self.assertEqual(guarded.returncode, 2)
        self.assertIn("architecture/", guarded.stderr)

    def test_existing_output_requires_force(self):
        diff = self.write("diff.json", diff_document())
        target = self.root / "packet.html"
        target.write_text("previous", encoding="utf-8")
        blocked = self.run_cli("--diff", str(diff), "--html", str(target))
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("already exists", blocked.stderr)
        forced = self.run_cli("--diff", str(diff), "--html", str(target), "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)

    def test_missing_invalid_and_unsupported_json_fail_closed(self):
        missing = self.run_cli("--diff", str(self.root / "absent.json"), "--html", str(self.root / "a.html"))
        self.assertEqual(missing.returncode, 2)
        broken = self.write("broken.json", None, raw="{not json")
        self.assertEqual(self.run_cli("--diff", str(broken), "--html", str(self.root / "a.html")).returncode, 2)
        future = self.write("future.json", diff_document(schemaVersion=2))
        self.assertEqual(self.run_cli("--diff", str(future), "--html", str(self.root / "a.html")).returncode, 2)
        unknown = diff_document()
        unknown["surprise"] = {}
        self.assertEqual(self.run_cli("--diff", str(self.write("unknown.json", unknown)),
                                      "--html", str(self.root / "a.html")).returncode, 2)
        self.assertEqual(self.run_cli("--diff", str(self.write("d.json", diff_document())),
                                      "--check", str(self.write("c.json", check_document(findings=[{"severity": "info"}]))),
                                      "--html", str(self.root / "a.html")).returncode, 2)

    def test_non_png_render_is_rejected(self):
        junk = self.root / "view.png"
        junk.write_bytes(b"not a png")
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--render", "recovery-prerequisites=" + str(junk),
                              "--html", str(self.root / "a.html"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a PNG", result.stderr)

    def test_no_shell_or_network_imports(self):
        source = (SCRIPTS / "render_review.py").read_text(encoding="utf-8")
        for forbidden in ("import subprocess", "import socket", "import urllib", "import http",
                          "os.system", "urllib.request"):
            self.assertNotIn(forbidden, source)


class ReviewFindingRegressions(PacketCase):
    """Regression checks for review packet rendering."""

    def view_only(self):
        diff = diff_document()
        diff["views"]["added"] = ["recovery-prerequisites"]
        return diff

    def test_headline_never_claims_a_missing_image_is_shown(self):
        result = self.packet(self.view_only())
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("no visual evidence for those views", page)
        self.assertNotIn("embedded below", page)
        self.assertNotIn("is shown below", page)
        shown = self.packet(self.view_only(), renders=["recovery-prerequisites"], extra=("--force",))
        self.assertEqual(shown.returncode, 0, shown.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("origin is not verified", page)
        self.assertNotIn("no visual evidence for those views", page)

    def test_parentheses_stay_readable_in_the_summary(self):
        diff = diff_document()
        diff["views"]["added"] = ["recovery-prerequisites"]
        markdown = self.root / "summary.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff)), "--markdown", str(markdown))
        self.assertEqual(result.returncode, 0, result.stderr)
        text = markdown.read_text(encoding="utf-8")
        self.assertIn("The reviewed delta is 1 view(s): recovery-prerequisites", text)
        self.assertNotIn("view\\(s\\)", text)

    def test_view_id_cannot_inject_markdown_links_or_break_table_cells(self):
        hostile = "x](https://evil.example)![pwn`|tail"
        diff = diff_document()
        diff["views"]["added"] = [hostile]
        markdown = self.root / "summary.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff)),
                              "--markdown", str(markdown),
                              "--render", hostile + "=" + str(self.png))
        self.assertEqual(result.returncode, 0, result.stderr)
        text = markdown.read_text(encoding="utf-8")
        lines = text.splitlines()
        image_lines = [line for line in lines if line.startswith("![")]
        self.assertEqual(len(image_lines), 1, image_lines)
        self.assertRegex(image_lines[0],
                         r"^!\[LikeC4 render of view .*\]\(summary-assets/[A-Za-z0-9._-]+\.png\)$")
        for line in lines:
            if line.startswith("|") or line.startswith("!["):
                continue
            self.assertIsNone(re.search(r"(?<!\\)\]\(", line), line)
            self.assertNotIn("![pwn", line)
        self.assertIn("\\](", text)
        self.assertIn("\\|", text)

    def test_markdown_assets_cannot_escape_into_architecture_and_leave_no_partials(self):
        (self.root / "architecture").mkdir()
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(self.root / "architecture" / "review.md"),
                              "--render", "recovery-prerequisites=" + str(self.png))
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "architecture" / "review.md").exists())
        self.assertFalse((self.root / "architecture" / "review-assets").exists())

    def test_unsafe_view_id_asset_names_are_rejected_before_writes(self):
        diff = diff_document()
        diff["views"]["added"] = [".."]
        markdown = self.root / "review.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff)),
                              "--markdown", str(markdown),
                              "--render", "..=" + str(self.png))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(markdown.exists())
        self.assertFalse((self.root / "review-assets").exists())

    def test_asset_name_collision_with_different_bytes_writes_nothing(self):
        other = self.root / "other.png"
        other.write_bytes(PNG_1X1 + b"\x00")
        markdown = self.root / "review.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(markdown),
                              "--render", "same view=" + str(self.png),
                              "--render", "same  view=" + str(other))
        self.assertEqual(result.returncode, 2)
        self.assertIn("same asset name", result.stderr)
        self.assertFalse(markdown.exists())

    def test_png_origin_is_never_presented_as_verified(self):
        result = self.packet(self.view_only(), renders=["recovery-prerequisites"])
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["renderAssurance"],
                         {"formatValidated": True, "originVerified": False, "exportBound": False})
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("caller-supplied PNG", page)
        self.assertIn("origin unverified", page)
        self.assertIn("cannot prove which compiler produced them", page)

    def test_caller_edited_tests_executed_true_is_flagged_not_trusted(self):
        result = self.packet(diff_document(), check=check_document(testsExecuted=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checkAssurance"],
                         {"testsExecutedSelfReported": True, "testsExecutedVerified": False})
        self.assertTrue(any("caller-supplied" in warning for warning in payload["warnings"]))
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("claims <code>testsExecuted=true</code>", page)
        self.assertIn("cannot be treated as execution evidence", page)


def change_document(**overrides):
    document = {
        "schemaVersion": 1,
        "id": "add-payments-adapter",
        "intent": "Authorize card payments through an external PSP without storing card data.",
        "scope": ["shop.api", "shop.pay"],
        "constraints": [{"id": "no-card-data", "statement": "Card data MUST NOT be stored by the shop.",
                         "durability": "change-only", "appliesTo": ["shop.pay"],
                         "verificationRefs": ["tests/test_payments.py"]}],
        "evidence": [{"element": "shop.pay", "path": "app/payments.py", "state": "declared",
                      "note": "Adapter source; execution is recorded separately."},
                     {"element": "shop.api", "path": "tests/test_retry_budget.py", "state": "planned",
                      "note": "Retry budget test not written yet."}],
        "alternatives": [
            {"id": "inline-psp-calls", "title": "Call the PSP from shop.api", "tradeoff": "Fewer units, but card scope leaks into the API."},
            {"id": "psp-sidecar", "title": "Local sidecar proxy", "tradeoff": "Isolation without a container boundary the model can show."},
            {"id": "adapter-container", "title": "Payment adapter container (chosen)", "tradeoff": "One more unit to operate, clean boundary."},
        ],
        "decision": "adapter-container",
        "rationale": "Card scope is separable and independently deployable.",
        "openQuestions": ["Which PSP contract version is pinned?"],
    }
    document.update(overrides)
    return document


class ChangeRecordTests(PacketCase):
    def packet_with_change(self, change, extra=()):
        return self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                            "--change", str(self.write("change.json", change)),
                            "--html", str(self.root / "packet.html"), *extra)

    def bound_diff(self, change_path):
        document = diff_document()
        document["reviewBinding"]["change"] = {
            "id": json.loads(Path(change_path).read_text())["id"],
            "sha256": __import__("hashlib").sha256(Path(change_path).read_bytes()).hexdigest(),
        }
        return document

    def test_alternatives_table_keeps_the_chosen_column_legible(self):
        change = self.write("change.json", change_document())
        diff = self.write("diff.json", self.bound_diff(change))
        result = self.run_cli("--diff", str(diff), "--change", str(change),
                              "--html", str(self.root / "packet.html"))
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn('<table class="alternatives">', page)
        self.assertIn("table.alternatives th:nth-child(3),table.alternatives td:nth-child(3){white-space:nowrap", page)
        self.assertIn("table.alternatives{min-width:36rem}", page)

    def test_constraints_and_evidence_tables_keep_metadata_intact(self):
        change = self.write("change.json", change_document())
        diff = self.write("diff.json", self.bound_diff(change))
        result = self.run_cli("--diff", str(diff), "--change", str(change),
                              "--html", str(self.root / "packet.html"))
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn('<table class="constraints">', page)
        self.assertIn('<table class="evidence">', page)
        self.assertIn("table.constraints,table.evidence{overflow-wrap:normal}", page)
        self.assertIn("table.constraints th,table.evidence th{white-space:nowrap}", page)
        self.assertIn("table.constraints td:nth-child(5)", page)
        self.assertIn("table.evidence td:nth-child(3){white-space:nowrap}", page)
        # long prose columns must keep wrapping
        self.assertNotIn("table.constraints td:nth-child(2)", page)
        self.assertNotIn("table.evidence td:nth-child(4)", page)

    def test_every_table_gets_a_horizontal_scroller(self):
        change = self.write("change.json", change_document())
        diff = self.write("diff.json", self.bound_diff(change))
        self.run_cli("--diff", str(diff), "--change", str(change),
                     "--html", str(self.root / "packet.html"))
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertEqual(page.count("<table"), page.count('<div class="table-scroll">'))
        self.assertIn(".table-scroll{overflow-x:auto", page)
        self.assertNotIn('<div class="table-scroll"><div class="table-scroll">', page)

    def test_bound_change_record_is_verified_and_labelled(self):
        change = self.write("change.json", change_document())
        diff = self.write("diff.json", self.bound_diff(change))
        result = self.run_cli("--diff", str(diff), "--change", str(change),
                              "--html", str(self.root / "packet.html"))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["changeBinding"]["bound"])
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("bound to the review fingerprint", page)
        self.assertNotIn("not bound to the review fingerprint", page)

    def test_altered_change_record_is_refused(self):
        change = self.write("change.json", change_document())
        diff = self.write("diff.json", self.bound_diff(change))
        altered = change_document(intent="A different intent swapped in after diff creation.")
        self.write("change.json", altered)
        result = self.run_cli("--diff", str(diff), "--change", str(change),
                              "--html", str(self.root / "packet.html"), "--force")
        self.assertEqual(result.returncode, 2)
        self.assertIn("do not match the review fingerprint", result.stderr)
        self.assertFalse((self.root / "packet.html").exists())

    def test_swapped_change_id_is_refused(self):
        change = self.write("change.json", change_document())
        diff = self.write("diff.json", self.bound_diff(change))
        other = self.write("other.json", change_document(id="other-change"))
        result = self.run_cli("--diff", str(diff), "--change", str(other),
                              "--html", str(self.root / "packet.html"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("id does not match", result.stderr)

    def test_unbound_change_record_is_labelled_not_silent(self):
        change = self.write("change.json", change_document())
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--change", str(change), "--html", str(self.root / "packet.html"))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["changeBinding"]["bound"])
        self.assertTrue(any("not bound to the review fingerprint" in warning for warning in payload["warnings"]))
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("This change record is not bound to the review fingerprint", page)

    def test_alternatives_constraints_and_evidence_are_rendered(self):
        result = self.packet_with_change(change_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        for expected in ("add-payments-adapter", "inline-psp-calls", "adapter-container",
                         "no-card-data", "Card data MUST NOT be stored", "declared", "planned",
                         "Which PSP contract version is pinned?", "author-declared, not approved"):
            self.assertIn(expected, page)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["change"], "add-payments-adapter")

    def test_markdown_lists_alternatives_and_evidence_states(self):
        markdown = self.root / "summary.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--change", str(self.write("change.json", change_document())),
                              "--markdown", str(markdown))
        self.assertEqual(result.returncode, 0, result.stderr)
        text = markdown.read_text(encoding="utf-8")
        self.assertIn("| Alternative | Trade-off | Chosen |", text)
        self.assertIn("adapter-container", text)
        self.assertIn("Evidence states are author claims", text)

    def test_hostile_change_text_is_escaped(self):
        change = change_document(intent="<script>alert(1)</script>",
                                 openQuestions=["<img src=x onerror=alert(2)>"])
        result = self.packet_with_change(change)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_unknown_change_field_and_bad_state_fail_closed(self):
        future = change_document(extraField="x")
        self.assertEqual(self.packet_with_change(future).returncode, 2)
        bad_state = change_document(evidence=[{"element": "shop.pay", "path": "app/payments.py", "state": "verified"}])
        self.assertEqual(self.packet_with_change(bad_state, extra=("--force",)).returncode, 2)

    def test_model_free_change_is_not_described_as_nothing_changed(self):
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--change", str(self.write("change.json", change_document())),
                              "--html", str(self.root / "packet.html"),
                              "--markdown", str(self.root / "summary.md"))
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "packet.html").read_text(encoding="utf-8")
        self.assertIn("No C4 model delta", page)
        self.assertIn("behavioral or configuration only", page)
        self.assertIn("proposal record", page)
        self.assertNotIn("contains no visual evidence", page)
        self.assertIn("No C4 model delta", (self.root / "summary.md").read_text(encoding="utf-8"))

    def test_change_file_is_an_input_and_cannot_be_overwritten(self):
        change = self.write("change.json", change_document())
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--change", str(change), "--html", str(change))
        self.assertEqual(result.returncode, 2)
        self.assertIn("overwrite an input", result.stderr)


class ArtifactHygieneTests(PacketCase):
    def test_deterministic_output(self):
        diff = self.write("diff.json", diff_document())
        first, second = self.root / "one.html", self.root / "two.html"
        for target in (first, second):
            result = self.run_cli("--diff", str(diff), "--html", str(target),
                                  "--render", "recovery-prerequisites=" + str(self.png))
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_html_only_run_leaves_no_extra_files(self):
        out = self.root / "out"
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--html", str(out / "packet.html"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([path.name for path in out.iterdir()], ["packet.html"])

    def test_markdown_summary_embeds_a_copied_render(self):
        markdown = self.root / "summary" / "review.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(markdown),
                              "--render", "recovery-prerequisites=" + str(self.png))
        self.assertEqual(result.returncode, 0, result.stderr)
        text = markdown.read_text(encoding="utf-8")
        self.assertIn("![LikeC4 render of view recovery", text)
        self.assertIn("review-assets/recovery-prerequisites.png", text)
        self.assertTrue((markdown.parent / "review-assets" / "recovery-prerequisites.png").is_file())

    def test_large_render_is_embedded_without_truncation(self):
        big = self.root / "big.png"
        big.write_bytes(PNG_1X1 + b"\x00" * 300_000)
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--html", str(self.root / "big.html"),
                              "--render", "recovery-prerequisites=" + str(big))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater((self.root / "big.html").stat().st_size, 300_000)

    def test_validate_helpers_reject_nonfinite_and_wrong_types(self):
        with self.assertRaises(render_review.InputError):
            render_review.validate_diff({"schemaVersion": 1})
        diff = diff_document()
        diff["fingerprint"] = "not-a-fingerprint"
        with self.assertRaises(render_review.InputError):
            render_review.validate_diff(deepcopy(diff))
        with self.assertRaises(render_review.InputError):
            render_review.validate_check(check_document(valid="yes"))


class SymlinkSafetyTests(PacketCase):
    """A planted temporary-file or target symlink must never redirect a write."""

    def setUp(self):
        super().setUp()
        self.canonical = self.root / "context.c4"
        self.canonical.write_text("canonical LikeC4 model\n", encoding="utf-8")

    def assert_canonical_intact(self):
        self.assertEqual(self.canonical.read_text(encoding="utf-8"), "canonical LikeC4 model\n")

    def test_planted_predictable_temp_symlink_is_not_followed(self):
        (self.root / ".packet.html.tmp").symlink_to(self.canonical)
        result = self.packet(diff_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_canonical_intact()
        self.assertIn("Architecture review", (self.root / "packet.html").read_text(encoding="utf-8"))

    def test_packet_output_symlink_is_refused(self):
        (self.root / "packet.html").symlink_to(self.canonical)
        result = self.packet(diff_document())
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not be a symlink", result.stderr)
        self.assert_canonical_intact()

    def test_markdown_output_symlink_is_refused(self):
        markdown = self.root / "review.md"
        markdown.symlink_to(self.canonical)
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(markdown))
        self.assertEqual(result.returncode, 2)
        self.assert_canonical_intact()

    def test_asset_symlink_is_refused_before_any_write(self):
        assets = self.root / "review-assets"
        assets.mkdir()
        (assets / "recovery-prerequisites.png").symlink_to(self.canonical)
        markdown = self.root / "review.md"
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(markdown),
                              "--render", "recovery-prerequisites=" + str(self.png))
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not be a symlink", result.stderr)
        self.assert_canonical_intact()
        self.assertFalse(markdown.exists())

    def test_no_stray_temporary_files_remain(self):
        result = self.packet(diff_document())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if ".tmp" in path.name), [])


class PartialWriteTests(PacketCase):
    """A late failure must not delete artifacts it already replaced under --force."""

    def blocker(self):
        """A directory at the HTML target: deterministic OSError inside os.replace."""
        target = self.root / "packet.html"
        target.mkdir()
        (target / "keep").write_text("occupied", encoding="utf-8")
        return target

    def test_forced_overwrite_is_kept_and_reported_as_partial(self):
        markdown = self.root / "review.md"
        markdown.write_text("PREVIOUS REVIEW\n", encoding="utf-8")
        self.blocker()
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(markdown), "--html", str(self.root / "packet.html"),
                              "--force")
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "partial")
        self.assertIn(str(markdown), payload["committedOutputs"])
        self.assertEqual(payload["removedOutputs"], [])
        self.assertNotEqual(markdown.read_text(encoding="utf-8"), "PREVIOUS REVIEW\n")
        self.assertIn("C4Spec review packet", markdown.read_text(encoding="utf-8"))
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if ".tmp" in path.name), [])

    def test_newly_created_artifacts_are_removed_and_reported(self):
        markdown = self.root / "review.md"
        self.blocker()
        result = self.run_cli("--diff", str(self.write("diff.json", diff_document())),
                              "--markdown", str(markdown), "--html", str(self.root / "packet.html"),
                              "--force")
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["committedOutputs"], [])
        self.assertIn(str(markdown), payload["removedOutputs"])
        self.assertFalse(markdown.exists())
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if ".tmp" in path.name), [])


if __name__ == "__main__":
    unittest.main()
