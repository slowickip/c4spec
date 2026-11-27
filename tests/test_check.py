import json
from copy import deepcopy
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "c4spec" / "scripts"))
from check import check, InputError  # noqa: E402


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.change = {"schemaVersion": 1, "id": "new-cache", "intent": "Reduce latency",
                       "scope": ["shop.api"]}
        self.model = {"projectId": "demo",
                      "elements": {"shop.api": {"id": "shop.api", "kind": "container",
                                                 "title": "API", "description": {"txt": "Serves requests"},
                                                 "technology": "Python"}},
                      "relations": {}, "views": {}}

    def findings(self, result):
        return {x["code"] for x in result["findings"]}

    def test_identical_duplicate_159_project_validates_in_both_phases(self):
        repeated = [self.model, deepcopy(self.model)]
        proposed = check(self.change, repeated, root=self.repo, phase="proposal")
        completed = check(self.change, repeated, root=self.repo, phase="completion")
        self.assertTrue(proposed["valid"])
        self.assertTrue(completed["valid"])
        self.assertFalse(completed["testsExecuted"])

    def test_multiple_projects_require_explicit_selector(self):
        other = deepcopy(self.model)
        other["projectId"] = "other"
        with self.assertRaisesRegex(InputError, "multiple project IDs"):
            check(self.change, [self.model, other], root=self.repo)
        chosen = check(self.change, [self.model, other], root=self.repo,
                       project_id="demo", phase="completion")
        self.assertTrue(chosen["valid"])
        with self.assertRaisesRegex(InputError, "not found"):
            check(self.change, [self.model, other], root=self.repo, project_id="missing")

    def test_conflicting_duplicate_project_is_rejected(self):
        conflicting = deepcopy(self.model)
        conflicting["elements"]["shop.api"]["title"] = "Changed"
        with self.assertRaisesRegex(InputError, "Conflicting duplicate"):
            check(self.change, [self.model, conflicting], root=self.repo)

    def test_minimal_proposal(self):
        report = check(self.change, self.model, root=self.repo)
        self.assertTrue(report["valid"])
        self.assertFalse(report["implementationConformanceVerified"])

    def test_model_only_needs_no_change_record_and_still_reports_quality(self):
        del self.model["elements"]["shop.api"]["description"]
        report = check(model=self.model, root=self.repo, phase="completion")
        self.assertTrue(report["valid"])
        self.assertIn("missing_responsibility", self.findings(report))
        self.assertFalse(report["testsExecuted"])

    def test_model_only_checks_existing_durable_constraint_targets(self):
        register = {"schemaVersion": 1, "constraints": [{
            "id": "existing-rule", "statement": "An existing obligation",
            "appliesTo": ["missing.element"], "verificationRefs": ["contract.py"]}]}
        (self.repo / "contract.py").write_text("# declared contract")
        report = check(model=self.model, constraints=register, root=self.repo)
        self.assertFalse(report["valid"])
        self.assertIn("unmapped_constraint", self.findings(report))

    def test_no_input_cannot_report_success(self):
        with self.assertRaisesRegex(InputError, "model-json"):
            check(root=self.repo)

    def test_alternatives_are_optional_but_require_three_routes_when_present(self):
        def route(index):
            return {"id": f"route-{index}", "tradeoff": f"tradeoff {index}"}

        self.assertTrue(check(self.change, self.model, root=self.repo)["valid"])
        two = {**self.change, "alternatives": [route(1), route(2)], "decision": "route-1"}
        report = check(two, self.model, root=self.repo)
        self.assertFalse(report["valid"])
        self.assertEqual({finding["code"] for finding in report["findings"]}, {"schema"})
        self.assertEqual(report["findings"][0]["location"], "change.alternatives")
        three = {**self.change, "alternatives": [route(1), route(2), route(3)], "decision": "route-1"}
        self.assertTrue(check(three, self.model, root=self.repo)["valid"])
        unknown = {**self.change, "alternatives": [route(1), route(2), route(3)], "decision": "route-9"}
        codes = {finding["code"] for finding in check(unknown, self.model, root=self.repo)["findings"]}
        self.assertIn("unknown_decision", codes)

    def test_schema_rejects_missing_id(self):
        del self.change["id"]
        self.assertFalse(check(self.change, root=self.repo)["valid"])

    def test_persistent_requires_verification_ref(self):
        self.change["constraints"] = [{"id": "fallback", "statement": "Remain available",
                                       "durability": "persistent"}]
        self.assertIn("verification_required", self.findings(check(self.change, root=self.repo)))

    def test_observed_evidence_requires_timestamp_and_event_context(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "verification.py").write_text("# test source", encoding="utf8")
        evidence = {"element": "shop.api", "path": "tests/verification.py", "state": "observed"}
        self.change["evidence"] = [evidence]
        no_timestamp = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertFalse(no_timestamp["valid"])
        self.assertIn("schema", self.findings(no_timestamp))

        evidence["observedAt"] = "2026-11-13T10:00:00Z"
        no_context = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertFalse(no_context["valid"])
        self.assertIn("schema", self.findings(no_context))

        evidence["note"] = "Local pytest run on feature revision; see associated CI for actual result"
        valid = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(valid["valid"], valid["findings"])
        self.assertFalse(valid["testsExecuted"])
        self.assertFalse(valid["runtimeVerified"])

    def test_declared_source_does_not_require_observation_timestamp(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "verification.py").write_text("# declared source", encoding="utf8")
        self.change["evidence"] = [{
            "element": "shop.api", "path": "tests/verification.py", "state": "declared"}]
        result = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(result["valid"], result["findings"])

    def test_planned_evidence(self):
        self.change["constraints"] = [{"id": "fallback", "statement": "Remain available",
                                       "durability": "persistent", "verificationRefs": ["tests/fallback.py"]}]
        self.change["evidence"] = [{"element": "shop.api", "path": "tests/fallback.py",
                                   "state": "planned"}]
        proposed = check(self.change, self.model, root=self.repo, phase="proposal")
        completed = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(proposed["valid"])
        self.assertFalse(completed["valid"])
        self.assertIn("still_planned", self.findings(completed))

    def test_unmapped_future_scope_is_warning_at_proposal_but_error_at_completion(self):
        self.change["scope"].append("shop.proposed-cache")
        proposed = check(self.change, self.model, root=self.repo, phase="proposal")
        completed = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(proposed["valid"])
        self.assertIn("unmapped_scope", self.findings(proposed))
        self.assertFalse(completed["valid"])
        self.assertIn("unmapped_scope", self.findings(completed))

    def test_unmapped_evidence_and_constraint_fail_completion(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests/contract.py").write_text("assert True", encoding="utf8")
        self.change["constraints"] = [{"id": "fallback", "statement": "Recover",
                                       "durability": "persistent", "appliesTo": ["shop.missing"],
                                       "verificationRefs": ["tests/contract.py"]}]
        self.change["evidence"] = [{"element": "shop.missing", "path": "tests/contract.py",
                                   "state": "declared"}]
        proposed = check(self.change, self.model, root=self.repo, phase="proposal")
        completed = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(proposed["valid"])
        self.assertFalse(completed["valid"])
        self.assertIn("unmapped_evidence", self.findings(completed))
        self.assertIn("unmapped_constraint", self.findings(completed))

    def test_completion_requires_computed_model(self):
        proposed = check(self.change, root=self.repo, phase="proposal")
        completed = check(self.change, root=self.repo, phase="completion")
        self.assertTrue(proposed["valid"])
        self.assertFalse(completed["valid"])
        self.assertIn("model_required", self.findings(completed))
    def test_completed_evidence_with_existing_file(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests/fallback.py").write_text("assert True", encoding="utf8")
        self.change["evidence"] = [{"element": "shop.api", "path": "tests/fallback.py",
                                   "state": "declared"}]
        self.assertTrue(check(self.change, self.model, root=self.repo, phase="completion")["valid"])

    def test_no_escape(self):
        self.change["evidence"] = [{"element": "shop.api", "path": "../secrets.txt", "state": "declared"}]
        self.assertIn("unsafe_path", self.findings(check(self.change, self.model, root=self.repo)))

    def test_model_warnings(self):
        self.model["elements"]["shop.api"]["description"] = {}
        self.model["relations"]["x"] = {"source": {"model": "shop.api"},
                                        "target": {"model": "shop.api"}, "kind": "sync"}
        report = check(self.change, self.model, root=self.repo)
        self.assertIn("missing_responsibility", self.findings(report))
        self.assertIn("unlabeled_relationship", self.findings(report))
        self.assertTrue(report["valid"])

    def test_completion_requires_persistent_constraint_verification_ref_to_match_evidence(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "real.py").write_text("# actual evidence", encoding="utf8")
        (self.repo / "tests" / "unrelated.py").write_text("# unrelated", encoding="utf8")
        self.change["constraints"] = [{
            "id": "fallback", "statement": "Remain available",
            "durability": "persistent", "appliesTo": ["shop.api"],
            "verificationRefs": ["tests/unrelated.py"],
        }]
        self.change["evidence"] = [{
            "element": "shop.api", "path": "tests/real.py", "state": "declared",
        }]
        proposed = check(self.change, self.model, root=self.repo, phase="proposal")
        completed = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(proposed["valid"])
        self.assertIn("unlinked_verification_ref", self.findings(proposed))
        self.assertFalse(completed["valid"])
        self.assertIn("unlinked_verification_ref", self.findings(completed))

    def test_complete_reference_link_is_structural_not_executed_tests(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "failure.py").write_text("raise AssertionError('failed')", encoding="utf8")
        self.change["constraints"] = [{
            "id": "fallback", "statement": "Remain available",
            "durability": "persistent", "appliesTo": ["shop.api"],
            "verificationRefs": ["tests/failure.py"],
        }]
        self.change["evidence"] = [{
            "element": "shop.api", "path": "tests/failure.py", "state": "declared",
        }]
        completed = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(completed["valid"])
        self.assertFalse(completed["testsExecuted"])
        self.assertFalse(completed["implementationConformanceVerified"])
        self.assertFalse(completed["runtimeVerified"])

    def test_persistent_constraint_must_match_supplied_register(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "fallback.py").write_text("# evidence", encoding="utf8")
        self.change["constraints"] = [{
            "id": "fallback", "statement": "Remain available",
            "durability": "persistent", "appliesTo": ["shop.api"],
            "verificationRefs": ["tests/fallback.py"]}]
        self.change["evidence"] = [{"element": "shop.api",
                                   "path": "tests/fallback.py", "state": "declared"}]
        register = {"schemaVersion": 1, "constraints": []}
        proposal = check(self.change, self.model, register, root=self.repo, phase="proposal")
        completion = check(self.change, self.model, register, root=self.repo, phase="completion")
        self.assertTrue(proposal["valid"])
        self.assertIn("unpromoted_constraint", self.findings(proposal))
        self.assertFalse(completion["valid"])
        self.assertIn("unpromoted_constraint", self.findings(completion))
        register["constraints"] = [{"id": "fallback", "statement": "Changed meaning",
                                    "appliesTo": ["shop.api"],
                                    "verificationRefs": ["tests/fallback.py"]}]
        stale = check(self.change, self.model, register, root=self.repo, phase="completion")
        self.assertFalse(stale["valid"])
        self.assertIn("constraint_register_mismatch", self.findings(stale))
        register["constraints"][0]["statement"] = "Remain available"
        matched = check(self.change, self.model, register, root=self.repo, phase="completion")
        self.assertTrue(matched["valid"], matched["findings"])
        self.assertFalse(matched["testsExecuted"])

    def test_completion_discloses_missing_register_without_claiming_promotion(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "fallback.py").write_text("# evidence", encoding="utf8")
        self.change["constraints"] = [{
            "id": "fallback", "statement": "Remain available",
            "durability": "persistent", "appliesTo": ["shop.api"],
            "verificationRefs": ["tests/fallback.py"]}]
        self.change["evidence"] = [{"element": "shop.api",
                                   "path": "tests/fallback.py", "state": "declared"}]
        report = check(self.change, self.model, root=self.repo, phase="completion")
        self.assertTrue(report["valid"])
        self.assertIn("register_not_checked", self.findings(report))
        self.assertFalse(report["testsExecuted"])

    def test_durable_register_references(self):
        register = {"schemaVersion": 1, "constraints": [{
            "id": "fallback", "statement": "Remain available",
            "appliesTo": ["shop.missing"], "verificationRefs": ["nonexistent.py"]}]}
        report = check(self.change, self.model, register, root=self.repo)
        self.assertIn("unmapped_constraint", self.findings(report))

    def test_duplicate_constraint_ids(self):
        self.change["constraints"] = [{"id": "a", "statement": "X", "durability": "change-only"},
                                       {"id": "a", "statement": "Y", "durability": "change-only"}]
        self.assertIn("duplicate_id", self.findings(check(self.change, self.model, root=self.repo)))


class BehaviorOnlyExampleTests(unittest.TestCase):
    """The mini-project carries one behavior-only change: no .c4 edit at all.

    These tests guard the two properties that make the case meaningful: the
    proposal/completion split is enforced by the record's evidence state, and a
    behavior-only change needs no model delta to be valid.
    """

    RECORD = ROOT / "examples/mini-project/c4spec/changes/expire-cache-entries.json"
    REGISTER = ROOT / "examples/mini-project/c4spec/constraints.json"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_order_cache.py").write_text("# evidence\n", encoding="utf-8")
        # The durable register is project-wide: every referenced path must resolve,
        # including constraints that belong to a different example change.
        (self.repo / "tests" / "test_db_config.py").write_text("# evidence\n", encoding="utf-8")
        (self.repo / "tests" / "test_cache_fallback.py").write_text("# evidence\n", encoding="utf-8")
        self.change = json.loads(self.RECORD.read_text(encoding="utf-8"))
        self.register = json.loads(self.REGISTER.read_text(encoding="utf-8"))
        self.model = {"projectId": "demo",
                      "elements": {"shop.api": {"id": "shop.api", "kind": "container",
                                                 "title": "Shop API", "technology": "Python",
                                                 "description": {"txt": "Serves requests"}}},
                      "relations": {}, "views": {}}

    def findings(self, result):
        return {(x["severity"], x["code"]) for x in result["findings"]}

    def test_shipped_record_is_structurally_complete_without_a_model_delta(self):
        report = check(self.change, self.model, self.register, root=self.repo, phase="completion")
        self.assertTrue(report["valid"], report["errors"])
        self.assertNotIn(("warning", "planned_path"), self.findings(report))

    def test_planned_test_reference_blocks_completion_but_not_proposal(self):
        self.change["evidence"][0].update({"state": "planned"})
        self.change["evidence"][0].pop("observedAt", None)
        (self.repo / "tests" / "test_order_cache.py").unlink()
        proposal = check(self.change, self.model, self.register, root=self.repo, phase="proposal")
        self.assertTrue(proposal["valid"])
        self.assertIn(("warning", "planned_path"), self.findings(proposal))
        completion = check(self.change, self.model, self.register, root=self.repo, phase="completion")
        self.assertFalse(completion["valid"])
        self.assertIn(("error", "still_planned"), self.findings(completion))

    def test_behavior_only_scope_never_needs_a_new_element(self):
        """scope names an existing element; nothing in the record asks for a node."""
        self.assertEqual(self.change["scope"], ["shop.api"])
        self.assertIn(self.change["scope"][0], self.model["elements"])
        report = check(self.change, self.model, self.register, root=self.repo, phase="completion")
        self.assertNotIn("unmapped_scope", {code for _, code in self.findings(report)})

    def test_example_model_has_no_cache_element(self):
        """Guards the case itself: the TTL bound must stay an implementation detail."""
        model = (ROOT / "examples/mini-project/architecture/shop.c4").read_text(encoding="utf-8")
        self.assertNotIn("cache", model.lower())


class ConfigOnlyExampleTests(unittest.TestCase):
    """The mini-project also carries a config-only change with a security edge.

    The point of the case is that "no architecture impact" must be argued, not
    assumed: the record carries the alternatives it rejected, and the validator
    is expected to stay silent about security while reporting that it ran nothing.
    """

    RECORD = ROOT / "examples/mini-project/c4spec/changes/require-tls-for-db.json"
    REGISTER = ROOT / "examples/mini-project/c4spec/constraints.json"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "app").mkdir()
        (self.repo / "tests").mkdir()
        (self.repo / "app" / "db_config.py").write_text("# config\n", encoding="utf-8")
        (self.repo / "tests" / "test_db_config.py").write_text("# evidence\n", encoding="utf-8")
        (self.repo / "tests" / "test_order_cache.py").write_text("# evidence\n", encoding="utf-8")
        (self.repo / "tests" / "test_cache_fallback.py").write_text("# evidence\n", encoding="utf-8")
        self.change = json.loads(self.RECORD.read_text(encoding="utf-8"))
        self.register = json.loads(self.REGISTER.read_text(encoding="utf-8"))
        self.model = {"projectId": "demo",
                      "elements": {"shop.api": {"id": "shop.api", "kind": "container",
                                                 "title": "Shop API", "technology": "Python",
                                                 "description": {"txt": "Serves requests"}}},
                      "relations": {}, "views": {}}

    def report(self, **kwargs):
        return check(self.change, self.model, self.register, root=self.repo, phase="completion", **kwargs)

    def test_completes_structurally_with_zero_model_delta(self):
        result = self.report()
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], 0)
        self.assertEqual(self.change["scope"], ["shop.api"])

    def test_reports_that_no_tests_or_runtime_were_verified(self):
        result = self.report()
        self.assertFalse(result["testsExecuted"])
        self.assertFalse(result["runtimeVerified"])
        self.assertFalse(result["implementationConformanceVerified"])

    def test_structural_and_security_impact_is_argued_in_the_record(self):
        ids = {a["id"] for a in self.change["alternatives"]}
        self.assertIn("model-tls-terminator", ids)
        self.assertIn("relabel-relation-technology", ids)
        self.assertIn(self.change["decision"], ids)
        self.assertTrue(self.change["openQuestions"], "a security change should keep its unknowns")

    def test_missing_evidence_for_a_verification_ref_fails_completion(self):
        self.change["evidence"] = [e for e in self.change["evidence"]
                                   if e["path"] != "tests/test_db_config.py"]
        result = self.report()
        self.assertFalse(result["valid"])
        self.assertIn("unlinked_verification_ref", {f["code"] for f in result["findings"]})

    def test_example_model_still_has_no_tls_element(self):
        model = (ROOT / "examples/mini-project/architecture/shop.c4").read_text(encoding="utf-8")
        self.assertNotIn("tls", model.lower())


class ArchitectureBoundaryExampleTests(unittest.TestCase):
    """The mini-project carries one *proposed* architecture change.

    broker + worker are independently running C4 containers, and nothing is implemented: the
    proposal must validate, must never pass completion, and the model must keep
    C4 container semantics (runnable, technology and responsibility stated).
    """

    RECORD = ROOT / "examples/mini-project/c4spec/changes/add-notification-worker.json"
    MODEL = ROOT / "examples/mini-project/architecture/shop.c4"
    REGISTER = ROOT / "examples/mini-project/c4spec/constraints.json"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "tests").mkdir()
        for name in ("test_order_cache.py", "test_db_config.py", "test_cache_fallback.py"):
            (self.repo / "tests" / name).write_text("# evidence\n", encoding="utf-8")
        self.change = json.loads(self.RECORD.read_text(encoding="utf-8"))
        self.register = json.loads(self.REGISTER.read_text(encoding="utf-8"))
        self.model = {"projectId": "demo",
                      "elements": {eid: {"id": eid, "kind": "container", "title": eid,
                                         "technology": "x", "description": {"txt": "y"}}
                                   for eid in ("shop.api", "shop.db", "shop.broker", "shop.worker")},
                      "relations": {}, "views": {}}

    def codes(self, phase):
        result = check(self.change, self.model, self.register, root=self.repo, phase=phase)
        return result, {(f["severity"], f["code"]) for f in result["findings"]}

    def test_proposal_is_valid_with_only_planned_reference_warnings(self):
        result, seen = self.codes("proposal")
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual({code for severity, code in seen if severity == "warning"}, {"planned_path"})
        self.assertFalse([f for f in result["findings"] if f["severity"] == "error"])

    def test_unimplemented_proposal_cannot_complete(self):
        result, seen = self.codes("completion")
        self.assertFalse(result["valid"])
        self.assertIn(("error", "still_planned"), seen)

    def test_new_containers_keep_c4_container_semantics(self):
        model = self.MODEL.read_text(encoding="utf-8")
        for eid, title in (("broker", "Message Broker"), ("worker", "Notification Worker")):
            block = re.search(rf"{eid} = container '{title}' \{{(.*?)\n    \}}", model, re.S)
            self.assertIsNotNone(block, f"{eid} must be a container")
            body = block.group(1) if block else ""
            self.assertIn("technology '", body)
            self.assertIn("description '", body)

    def test_scope_matches_modeled_elements(self):
        model = self.MODEL.read_text(encoding="utf-8")
        for eid in self.change["scope"]:
            self.assertIn(eid.split(".", 1)[1], model)

    def test_consequential_choice_lists_at_least_three_routes(self):
        ids = {a["id"] for a in self.change["alternatives"]}
        self.assertGreaterEqual(len(ids), 3)
        self.assertIn(self.change["decision"], ids)


class AppliedCacheFallbackTests(unittest.TestCase):
    """`add-cache` completed: planned evidence became declared, constraint promoted.

    Guards the apply→verify→finish contract for a behavior-only change: the
    completion check validates structure only, and the durability rule is that a
    promoted constraint keeps exactly the references its record declares.
    """

    RECORD = ROOT / "examples/mini-project/c4spec/changes/add-cache.json"
    REGISTER = ROOT / "examples/mini-project/c4spec/constraints.json"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "app").mkdir()
        (self.repo / "tests").mkdir()
        for name in ("test_cache_fallback.py", "test_order_cache.py", "test_db_config.py"):
            (self.repo / "tests" / name).write_text("# evidence\n", encoding="utf-8")
        (self.repo / "app" / "product_reads.py").write_text("# fixture\n", encoding="utf-8")
        self.change = json.loads(self.RECORD.read_text(encoding="utf-8"))
        self.register = json.loads(self.REGISTER.read_text(encoding="utf-8"))
        self.model = {"projectId": "demo",
                      "elements": {"shop.api": {"id": "shop.api", "kind": "container",
                                                 "title": "Shop API", "technology": "Python",
                                                 "description": {"txt": "Serves requests"}}},
                      "relations": {}, "views": {}}

    def report(self, phase="completion"):
        return check(self.change, self.model, self.register, root=self.repo, phase=phase)

    def test_completion_passes_with_zero_model_delta(self):
        result = self.report()
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], 0)

    def test_completion_still_reports_that_no_tests_were_executed(self):
        result = self.report()
        self.assertFalse(result["testsExecuted"])
        self.assertFalse(result["runtimeVerified"])

    def test_evidence_is_declared_and_points_at_real_fixture_files(self):
        states = {e["path"]: e["state"] for e in self.change["evidence"]}
        self.assertEqual(states.get("tests/test_cache_fallback.py"), "declared")
        self.assertEqual(states.get("app/product_reads.py"), "declared")
        self.assertNotIn("planned", states.values())

    def test_constraint_is_promoted_once_with_the_record_reference(self):
        ids = [c["id"] for c in self.register["constraints"]]
        self.assertEqual(ids.count("cache-fallback"), 1, "no duplication in the register")
        promoted = next(c for c in self.register["constraints"] if c["id"] == "cache-fallback")
        recorded = self.change["constraints"][0]
        self.assertEqual(promoted["verificationRefs"], recorded["verificationRefs"])
        self.assertEqual(promoted["appliesTo"], recorded["appliesTo"])

    def test_model_keeps_zero_architecture_delta(self):
        model = (ROOT / "examples/mini-project/architecture/shop.c4").read_text(encoding="utf-8")
        self.assertNotIn("cache", model.lower())


if __name__ == "__main__":
    unittest.main()
