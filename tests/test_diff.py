from copy import deepcopy
from pathlib import Path
import json
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".agents" / "skills" / "c4spec" / "scripts"))
from diff import compare, load, select_project  # noqa: E402


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "projectId": "demo",
            "elements": {"app": {"id": "app", "kind": "container",
                                 "title": "App", "style": {"color": "blue"}}},
            "relations": {"r1": {"id": "r1", "source": {"model": "app"},
                                 "target": {"model": "app"}, "kind": "sync",
                                 "title": "Calls itself"}},
            "views": {"overview": {"id": "overview", "title": "Overview",
                                   "nodes": [{"id": "app", "x": 10}]}}
        }

    def test_shared_selector_accepts_duplicate_object_records(self):
        self.assertEqual(select_project([self.base, deepcopy(self.base)]), self.base)

    def test_shared_selector_rejects_conflicting_duplicates(self):
        changed = deepcopy(self.base)
        changed["elements"]["app"]["title"] = "Another"
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            select_project([self.base, changed])

    def test_repeated_identical_159_export_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text(json.dumps([self.base, deepcopy(self.base)]), encoding="utf-8")
            loaded = load(path)
            self.assertEqual(loaded["projectId"], "demo")
            self.assertEqual(compare(loaded, self.base)["elements"]["modified"], [])

    def test_export_with_multiple_project_ids_requires_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "projects.json"
            other = deepcopy(self.base)
            other["projectId"] = "other"
            path.write_text(json.dumps([self.base, other]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "multiple project IDs"):
                load(path)
            self.assertEqual(load(path, "demo")["projectId"], "demo")
            self.assertEqual(load(path, "other")["projectId"], "other")
            with self.assertRaisesRegex(ValueError, "not found"):
                load(path, "missing")

    def test_conflicting_repeated_project_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conflict.json"
            changed = deepcopy(self.base)
            changed["elements"]["app"]["title"] = "Different responsibility"
            path.write_text(json.dumps([self.base, changed]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
                load(path)

    def test_empty_and_invalid_exports_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no projects"):
                load(path)
            path.write_text('[{"projectId":"demo"}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Expected computed"):
                load(path)

    def test_self_comparison(self):
        result = compare(self.base, deepcopy(self.base))
        self.assertEqual(result["elements"]["added"], [])
        self.assertEqual(result["views"]["modified"], [])
        self.assertEqual(result["relationships"]["added"], [])

    def test_layout_ignored(self):
        head = deepcopy(self.base)
        head["elements"]["app"]["style"]["color"] = "red"
        head["views"]["overview"]["nodes"][0]["x"] = 400
        self.assertEqual(compare(self.base, head)["elements"]["modified"], [])
        self.assertEqual(compare(self.base, head)["views"]["modified"], [])

    def test_added_element_and_parallel_relation(self):
        head = deepcopy(self.base)
        head["elements"]["cache"] = {"id": "cache", "kind": "container", "title": "Cache"}
        head["relations"]["r2"] = {**head["relations"]["r1"], "id": "r2"}
        result = compare(self.base, head)
        self.assertEqual(result["elements"]["added"], ["cache"])
        self.assertEqual(result["relationships"]["added"][0]["count"], 1)

    def test_relationship_technology_edit_is_not_topology_change(self):
        head = deepcopy(self.base)
        head["relations"]["r1"]["technology"] = "SQL over TLS"
        result = compare(self.base, head)
        self.assertEqual(result["relationships"]["added"], [])
        self.assertEqual(result["relationships"]["removed"], [])
        changed = result["relationships"]["modified"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["fieldChanges"]["technology"]["after"], "SQL over TLS")
        self.assertFalse(changed[0]["fieldChanges"]["technology"]["beforePresent"])

    def test_relationship_endpoint_change_remains_remove_and_add(self):
        head = deepcopy(self.base)
        head["relations"]["r1"]["target"] = {"model": "new-db"}
        result = compare(self.base, head)["relationships"]
        self.assertEqual(result["modified"], [])
        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(len(result["removed"]), 1)

    def test_ambiguous_parallel_relation_edits_are_not_guessed(self):
        base = deepcopy(self.base)
        base["relations"]["r2"] = {**base["relations"]["r1"], "id": "r2", "title": "Reads"}
        head = deepcopy(base)
        head["relations"]["r1"]["technology"] = "SQL over TLS"
        result = compare(base, head)["relationships"]
        self.assertEqual(result["modified"], [])
        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(len(result["removed"]), 1)

    def test_relation_name_edit_keeps_field_before_after_and_fingerprint(self):
        head = deepcopy(self.base)
        head["relations"]["r1"]["title"] = "Calls self over TLS"
        changed = compare(self.base, head)
        self.assertEqual(changed["relationships"]["added"], [])
        self.assertEqual(changed["relationships"]["modified"][0]["fieldChanges"]["title"]["before"], "Calls itself")
        self.assertEqual(changed["relationships"]["modified"][0]["fieldChanges"]["title"]["after"], "Calls self over TLS")
        self.assertNotEqual(changed["fingerprint"], compare(self.base, self.base)["fingerprint"])

    def test_added_elements_include_c4_responsibility_and_technology(self):
        head = deepcopy(self.base)
        head["elements"]["shop.broker"] = {
            "id": "shop.broker", "kind": "container",
            "title": "Message Broker", "technology": "RabbitMQ",
            "description": {"txt": "Stores order events for asynchronous processing"},
            "style": {"color": "green"},
        }
        result = compare(self.base, head)
        self.assertEqual(result["elements"]["added"], ["shop.broker"])
        summary = result["elements"]["addedDetails"]["shop.broker"]
        self.assertEqual(summary["title"], "Message Broker")
        self.assertEqual(summary["technology"], "RabbitMQ")
        self.assertEqual(summary["description"]["txt"], "Stores order events for asynchronous processing")
        self.assertEqual(summary["kind"], "container")
        self.assertNotIn("style", summary)

    def test_removed_elements_include_same_summary(self):
        head = deepcopy(self.base)
        head["elements"].pop("app")
        result = compare(self.base, head)
        self.assertEqual(result["elements"]["removed"], ["app"])
        self.assertEqual(result["elements"]["removedDetails"]["app"]["title"], "App")

    def test_generated_index_is_visible_but_flagged_for_review(self):
        head = deepcopy(self.base)
        head["views"]["index"] = {"id": "index", "title": "Landscape", "nodes": [{"id": "app"}]}
        result = compare(self.base, head)
        self.assertIn("index", result["views"]["added"])
        self.assertTrue(any("index" in text for text in result["reviewHints"]))

    def test_view_only_membership_is_reported(self):
        head = deepcopy(self.base)
        head["views"]["overview"]["nodes"].append({"id": "db", "modelRef": "db", "x": 300})
        self.assertEqual(compare(self.base, head)["views"]["modified"], ["overview"])

    def test_view_edges_detect_semantic_changes_without_model_delta(self):
        self.base["views"]["overview"]["edges"] = [
            {"id": "e1", "source": "app", "target": "app", "relations": ["r1"]},
        ]
        head = deepcopy(self.base)
        head["views"]["overview"]["edges"] = []
        result = compare(self.base, head)
        self.assertEqual(result["views"]["modified"], ["overview"])
        self.assertEqual(result["relationships"]["added"], [])

    def test_dynamic_step_binding_changes_even_when_step_ids_do_not(self):
        self.base["views"]["overview"].update({
            "_type": "dynamic",
            "edges": [{"id": "s1", "source": "app", "target": "app", "title": "Authenticate"},
                      {"id": "s2", "source": "app", "target": "app", "title": "Notify"}],
            "flow": ["s1", "s2"],
        })
        head = deepcopy(self.base)
        head["views"]["overview"]["edges"][0]["title"] = "Notify"
        head["views"]["overview"]["edges"][1]["title"] = "Authenticate"
        result = compare(self.base, head)
        self.assertEqual(result["views"]["modified"], ["overview"])

    def test_view_layout_only_remains_ignored(self):
        head = deepcopy(self.base)
        head["views"]["overview"]["nodes"][0]["x"] = 600
        head["views"]["overview"]["nodes"][0]["color"] = "red"
        self.assertEqual(compare(self.base, head)["views"]["modified"], [])
    def test_dynamic_order_changes(self):
        head = deepcopy(self.base)
        self.base["views"]["overview"]["flow"] = ["first", "second"]
        head["views"]["overview"]["flow"] = ["second", "first"]
        self.assertEqual(compare(self.base, head)["views"]["modified"], ["overview"])

    def test_different_projects_fail(self):
        head = deepcopy(self.base)
        head["projectId"] = "other"
        with self.assertRaises(ValueError):
            compare(self.base, head)

    def test_content_sensitive_fingerprint_and_field_values(self):
        first = deepcopy(self.base)
        first["elements"]["app"]["technology"] = "Cilium 1.20.4"
        second = deepcopy(self.base)
        second["elements"]["app"]["technology"] = "Cilium (kube-proxy retained)"
        a, b = compare(self.base, first), compare(self.base, second)
        self.assertEqual(a["elements"]["modified"], ["app"])
        self.assertEqual(b["elements"]["modified"], ["app"])
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])
        self.assertEqual(a["elements"]["fieldChanges"]["app"]["technology"]["after"], "Cilium 1.20.4")
        self.assertFalse(a["elements"]["fieldChanges"]["app"]["technology"]["beforePresent"])
        self.assertTrue(a["elements"]["fieldChanges"]["app"]["technology"]["afterPresent"])

    def test_added_elements_with_same_id_but_different_details_hash_differently(self):
        a = deepcopy(self.base)
        b = deepcopy(self.base)
        a["elements"]["cache"] = {"id": "cache", "kind": "container", "title": "Cache A"}
        b["elements"]["cache"] = {"id": "cache", "kind": "container", "title": "Cache B"}
        self.assertEqual(compare(self.base, a)["elements"]["added"], ["cache"])
        self.assertEqual(compare(self.base, b)["elements"]["added"], ["cache"])
        self.assertNotEqual(compare(self.base, a)["fingerprint"], compare(self.base, b)["fingerprint"])

    def test_layout_only_change_does_not_change_fingerprint(self):
        head = deepcopy(self.base)
        head["views"]["overview"]["nodes"][0]["x"] = 999
        head["elements"]["app"]["style"]["color"] = "green"
        self.assertEqual(compare(self.base, self.base)["fingerprint"], compare(self.base, head)["fingerprint"])

    def test_changed_base_value_changes_fingerprint(self):
        old = deepcopy(self.base)
        old["elements"]["app"]["title"] = "Old name"
        new = deepcopy(self.base)
        new["elements"]["app"]["title"] = "New name"
        self.assertNotEqual(compare(old, new)["fingerprint"], compare(self.base, new)["fingerprint"])

    def test_stable_fingerprint(self):
        self.assertEqual(compare(self.base, deepcopy(self.base))["fingerprint"],
                         compare(self.base, deepcopy(self.base))["fingerprint"])


if __name__ == "__main__":
    unittest.main()
