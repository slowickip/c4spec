"""Offline tests for the inline native-diff Mermaid overlay.

No LikeC4 binary, no network: the fixtures mirror the shape of
``likec4 export json --skip-layout`` for the mini-project, and the assertions
pin the two properties that make the overlay trustworthy — identity-based
matching and agreement with LikeC4's own per-view counts.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("native_inline_diff", HERE / "inline_diff.py")
assert SPEC and SPEC.loader
inline = importlib.util.module_from_spec(SPEC)
# dataclasses resolve `cls.__module__` through sys.modules while the module runs.
sys.modules[SPEC.name] = inline
SPEC.loader.exec_module(inline)

SHA = "a" * 40


def node(node_id, title, *, children=(), tags=(), kind="container", description="", shape="rectangle"):
    return {"id": node_id, "title": title, "kind": kind, "notation": "Container",
            "shape": shape, "color": "primary", "tags": list(tags), "children": list(children),
            "description": {"txt": description} if description else None, "level": 0}


def edge(edge_id, source, target, label, *, line="dashed", description=""):
    return {"id": edge_id, "source": source, "target": target, "label": label,
            "line": line, "head": "normal", "color": "gray",
            "description": {"txt": description} if description else None, "relations": []}


def view(view_id, nodes, edges, *, title="View", type_="element"):
    return {"id": view_id, "title": title, "_type": type_, "nodes": nodes, "edges": edges}


CUSTOMER = node("customer", "Customer", kind="person", shape="rectangle")
SHOP = node("shop", "Online Shop", children=["shop.api", "shop.broker", "shop.worker"], kind="system")
API = node("shop.api", "Shop API")
BROKER = node("shop.broker", "Message Broker")
WORKER = node("shop.worker", "Notification Worker")
V2 = node("shop.workerV2", "Notification Worker V2")

BASE_NODES = [CUSTOMER, SHOP, API, BROKER, WORKER]
BASE_EDGES = [
    edge("e1", "customer", "shop.api", "Browses products"),
    edge("e2", "shop.api", "shop.broker", "Publishes order events"),
    edge("e3", "shop.broker", "shop.worker", "Provides order events for consumption"),
    edge("e4", "shop.worker", "customer", "Sends order notifications"),
]
TOBE_NODES = [CUSTOMER, node("shop", "Online Shop", children=["shop.api", "shop.broker", "shop.workerV2"],
                            kind="system"), API, BROKER, V2]
TOBE_EDGES = [
    edge("e1", "customer", "shop.api", "Browses products"),
    edge("e2", "shop.api", "shop.broker", "Publishes order events"),
    edge("e5", "shop.broker", "shop.workerV2", "Delivers notification events"),
    edge("e6", "shop.workerV2", "customer", "Sends notifications"),
]
CLI_VIEW = {"id": "notifications", "title": "L2 — Notifications",
            "nodes": {"added": 1, "removed": 1, "modified": 0},
            "edges": {"added": 2, "removed": 2, "modified": 0}}


def docs(asis_view=None, tobe_view=None):
    asis = {"views": {"notifications": asis_view or view("notifications", BASE_NODES, BASE_EDGES)}}
    tobe = {"views": {"notifications": tobe_view or view("notifications", TOBE_NODES, TOBE_EDGES)}}
    return asis, tobe


class OverlayClassificationTests(unittest.TestCase):
    def test_replacement_matches_likec4_counts(self):
        overlay = inline.build_overlay(*docs(), "notifications", CLI_VIEW)
        self.assertEqual(overlay.counts, {"nodes": {"added": 1, "removed": 1, "modified": 0},
                                          "edges": {"added": 2, "removed": 2, "modified": 0}})
        states = {n["id"]: n["state"] for n in overlay.nodes}
        self.assertEqual(states["shop.worker"], "removed")
        self.assertEqual(states["shop.workerV2"], "added")
        self.assertEqual(states["shop.api"], "unchanged")
        # Both the retired worker and its replacement stay inside the container.
        self.assertEqual(overlay.children["shop"], ["shop.api", "shop.broker", "shop.worker", "shop.workerV2"])

    def test_requires_agreement_with_reported_counts(self):
        wrong = {**CLI_VIEW, "edges": {"added": 2, "removed": 1, "modified": 0}}
        with self.assertRaisesRegex(inline.UnsupportedFixture, "disagree"):
            inline.build_overlay(*docs(), "notifications", wrong)

    def test_refuses_when_the_diff_changes_nothing_visible(self):
        same = view("notifications", BASE_NODES, BASE_EDGES)
        with self.assertRaisesRegex(inline.UnsupportedFixture, "no visible change"):
            inline.build_overlay(*docs(same, view("notifications", BASE_NODES, BASE_EDGES)),
                                 "notifications",
                                 {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
                                  "edges": {"added": 0, "removed": 0, "modified": 0}})

    def test_modified_node_and_edge_are_matched_not_added(self):
        tagged = node("customer", "Customer", tags=["external"], kind="person")
        asis = view("notifications", BASE_NODES, BASE_EDGES)
        tobe = view("notifications", [tagged, SHOP, API, BROKER, WORKER],
                    [edge("e1", "customer", "shop.api", "Browses"),
                     edge("e2", "shop.api", "shop.broker", "Publishes order events"),
                     edge("e3", "shop.broker", "shop.worker", "Provides order events for consumption"),
                     edge("e4", "shop.worker", "customer", "Sends order notifications")])
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 1},
               "edges": {"added": 0, "removed": 0, "modified": 1}}
        overlay = inline.build_overlay(*docs(asis, tobe), "notifications", cli)
        self.assertEqual(overlay.counts["nodes"], {"added": 0, "removed": 0, "modified": 1})
        self.assertEqual(overlay.counts["edges"], {"added": 0, "removed": 0, "modified": 1})

    def test_parallel_edges_are_matched_individually(self):
        asis_edges = BASE_EDGES + [edge("e7", "shop.worker", "customer", "Escalates to support")]
        tobe_edges = BASE_EDGES + [edge("e8", "shop.worker", "customer", "Escalates to on-call")]
        # One of the two parallel edges keeps its label; the other is rewritten.
        tobe = view("notifications", BASE_NODES, tobe_edges)
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 0, "modified": 1}}
        overlay = inline.build_overlay(*docs(view("notifications", BASE_NODES, asis_edges), tobe),
                                       "notifications", cli)
        self.assertEqual(overlay.counts["edges"], {"added": 0, "removed": 0, "modified": 1})
        labels = [e.get("label") for e in overlay.edges if e["source"] == "shop.worker"]
        self.assertEqual(sorted(labels), ["Escalates to on-call", "Sends order notifications"])

    def test_removing_one_parallel_edge_is_a_removal_not_a_modification(self):
        asis_edges = BASE_EDGES + [edge("e7", "shop.worker", "customer", "Escalates to support")]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 1, "modified": 0}}
        overlay = inline.build_overlay(*docs(view("notifications", BASE_NODES, asis_edges),
                                             view("notifications", BASE_NODES, BASE_EDGES)),
                                       "notifications", cli)
        self.assertEqual(overlay.counts["edges"], {"added": 0, "removed": 1, "modified": 0})

    def test_ambiguous_parallel_rematch_is_refused_in_any_order(self):
        base = [node("c", "Customer", kind="person"), node("w", "Worker")]
        left = [edge("e1", "c", "w", "old-one"), edge("e2", "c", "w", "old-two")]
        right = [edge("e3", "c", "w", "new-one"), edge("e4", "c", "w", "new-two")]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 0, "modified": 2}}
        for order, candidate in (("ordered", right), ("shuffled", list(reversed(right)))):
            with self.subTest(order=order):
                with self.assertRaisesRegex(inline.UnsupportedFixture, "ambiguous parallel"):
                    inline.build_overlay(*docs(view("notifications", base, left),
                                               view("notifications", base, candidate)),
                                         "notifications", cli)

    def test_indistinguishable_parallel_duplicates_render_deterministically(self):
        # Two duplicates on each side: every pairing produces the same diagram,
        # so the order of the provider's edge list must not change the output.
        base = [node("c", "Customer", kind="person"), node("w", "Worker")]
        left = [edge("e1", "c", "w", "old"), edge("e2", "c", "w", "old")]
        right = [edge("e3", "c", "w", "new"), edge("e4", "c", "w", "new")]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 0, "modified": 2}}
        rendered = []
        for candidate in (right, list(reversed(right))):
            overlay = inline.build_overlay(*docs(view("notifications", base, left),
                                                 view("notifications", base, candidate)),
                                           "notifications", cli)
            self.assertEqual(overlay.counts["edges"], {"added": 0, "removed": 0, "modified": 2})
            rendered.append(inline.render_overlay(overlay))
        self.assertEqual(rendered[0], rendered[1])

    def test_single_parallel_rematch_still_counts_as_modified(self):
        base = [node("c", "Customer", kind="person"), node("w", "Worker")]
        left = [edge("e1", "c", "w", "old-only")]
        right = [edge("e2", "c", "w", "new-only")]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 0, "modified": 1}}
        overlay = inline.build_overlay(*docs(view("notifications", base, left),
                                             view("notifications", base, right)),
                                       "notifications", cli)
        self.assertEqual([e["state"] for e in overlay.edges], ["modified"])

    def test_rewritten_parallel_relations_are_refused_not_guessed(self):
        # Measured against likec4 1.61.0: two relations between the same
        # endpoints collapse into one view edge labelled ``[...]``, and rewriting
        # both titles is still reported as one *modified* edge while the exported
        # edges stay byte-identical. The export carries no relation identity
        # (ids are regenerated per export), so this must refuse, not guess.
        base = [node("c", "Customer", kind="person"), node("w", "Worker")]
        collapsed = [edge("1kpg20i", "c", "w", "[...]")]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 0, "modified": 1}}
        with self.assertRaisesRegex(inline.UnsupportedFixture, "disagree"):
            inline.build_overlay(*docs(view("notifications", base, collapsed),
                                       view("notifications", base, collapsed)),
                                 "notifications", cli)

    def test_refuses_non_element_views(self):
        dynamic = view("notifications", BASE_NODES, BASE_EDGES, type_="dynamic")
        with self.assertRaisesRegex(inline.UnsupportedFixture, "element view"):
            inline.build_overlay(*docs(dynamic, dynamic), "notifications", CLI_VIEW)

    def test_refuses_oversized_views(self):
        many = [node(f"n{i}", f"Node {i}") for i in range(inline.MAX_NODES + 1)]
        cli = {**CLI_VIEW, "nodes": {"added": 1, "removed": 0, "modified": 0},
               "edges": {"added": 0, "removed": 0, "modified": 0}}
        with self.assertRaisesRegex(inline.UnsupportedFixture, "exceed the inline bound"):
            inline.build_overlay(*docs(view("notifications", many, []),
                                       view("notifications", many + [node("extra", "Extra")], [])),
                                 "notifications", cli)

    def test_refuses_node_whose_parent_differs_even_when_counts_agree(self):
        # One unrelated node is modified, so the provider count gate passes and
        # only the containment check can catch the contradictory hierarchy.
        asis_nodes = [node("a", "Box A", children=["x"]), node("b", "Box B"),
                      node("x", "Child"), node("z", "Other")]
        tobe_nodes = [node("a", "Box A"), node("b", "Box B", children=["x"]),
                      node("x", "Child"), node("z", "Other", tags=["external"])]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 1},
               "edges": {"added": 0, "removed": 0, "modified": 0}}
        with self.assertRaisesRegex(inline.UnsupportedFixture, "contradictory containment"):
            inline.build_overlay(*docs(view("notifications", asis_nodes, []),
                                       view("notifications", tobe_nodes, [])),
                                 "notifications", cli)

    def test_refuses_cyclic_containment(self):
        cyc = [node("p", "P", children=["q"]), node("q", "Q", children=["p"]),
               node("z", "Other")]
        tobe = [node("p", "P", children=["q"]), node("q", "Q", children=["p"]),
                node("z", "Other", tags=["external"])]
        cli = {**CLI_VIEW, "nodes": {"added": 0, "removed": 0, "modified": 1},
               "edges": {"added": 0, "removed": 0, "modified": 0}}
        with self.assertRaisesRegex(inline.UnsupportedFixture, "cyclic containment"):
            inline.build_overlay(*docs(view("notifications", cyc, []),
                                       view("notifications", tobe, [])),
                                 "notifications", cli)


class OverlayRenderingTests(unittest.TestCase):
    def overlay(self, asis=None, tobe=None, cli=CLI_VIEW):
        return inline.build_overlay(*docs(asis, tobe), "notifications", cli)

    def comment(self, overlays=None):
        return inline.render_comment(overlays or [self.overlay()], repo="example-owner/c4spec",
                                     run_id=42, sha=SHA, artifact="native-diff-as-is-changes-to-be")

    def test_comment_carries_marker_identity_and_one_block(self):
        text = self.comment()
        self.assertTrue(text.startswith(inline.MARKER))
        self.assertIn(SHA, text)
        self.assertIn("https://github.com/example-owner/c4spec/actions/runs/42", text)
        self.assertIn("native-diff-as-is-changes-to-be", text)
        self.assertEqual(text.count("```mermaid"), 1)
        self.assertIn("flowchart TB", text)
        self.assertIn("Notification Worker V2", text)
        self.assertIn(":::removed", text)
        self.assertIn(":::added", text)

    def test_render_marks_both_edge_directions_with_linkstyle(self):
        block = inline.render_overlay(self.overlay())
        self.assertIn("linkStyle", block)
        added = [line for line in block.splitlines() if "stroke:#16a34a" in line]
        removed = [line for line in block.splitlines() if "stroke:#dc2626" in line]
        self.assertTrue(added and removed)

    def test_changed_boundaries_use_the_theme_background(self):
        empty = view("notifications", [], [])
        populated = view("notifications", BASE_NODES, BASE_EDGES)
        for before, after, stroke in ((empty, populated, "#16a34a"),
                                      (populated, empty, "#dc2626")):
            with self.subTest(stroke=stroke):
                overlay = inline.build_view_overlay(before, after, "notifications", "Notifications")
                block = inline.render_overlay(overlay)
                self.assertIn(f"style n1 fill:transparent,stroke:{stroke},stroke-width:2px", block)

    def test_hostile_labels_cannot_break_out_of_the_block(self):
        nasty = node("customer", 'A "quoted" <script>alert(1)</script> | `tick`',
                     kind="person", description="x")
        asis = view("notifications", BASE_NODES, BASE_EDGES)
        tobe = view("notifications", [nasty, SHOP, API, BROKER, V2],
                    [edge("e1", "customer", "shop.api", '<img src=x onerror=alert(1)> | "q"'),
                     edge("e2", "shop.api", "shop.broker", "Publishes order events"),
                     edge("e5", "shop.broker", "shop.workerV2", "Delivers"),
                     edge("e6", "shop.workerV2", "customer", "Sends")])
        cli = {**CLI_VIEW, "nodes": {"added": 1, "removed": 1, "modified": 1},
               "edges": {"added": 2, "removed": 2, "modified": 1}}
        text = inline.render_comment([inline.build_overlay(*docs(asis, tobe), "notifications", cli)],
                                     repo="example-owner/c4spec", run_id=42, sha=SHA)
        self.assertNotIn("<script>", text)
        self.assertNotIn("<img", text)
        # Hostile text survives only as escaped text, never as markup.
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", text)
        self.assertIn("&quot;quoted&quot;", text)
        self.assertEqual(text.count("```"), 2)

    def test_hostile_view_title_stays_out_of_markdown_markup(self):
        hostile = "@reviewer [click](https://example.invalid) *bold* `code` <b>x</b>"
        base = [node("c", "Customer", kind="person"), node("w", "Worker")]
        cli = {**CLI_VIEW, "title": hostile, "nodes": {"added": 0, "removed": 0, "modified": 0},
               "edges": {"added": 1, "removed": 0, "modified": 0}}
        overlay = inline.build_overlay(
            *docs(view("notifications", base, [edge("e1", "c", "w", "same")]),
                  view("notifications", base, [edge("e1", "c", "w", "same"),
                                               edge("e9", "c", "w", "added")])),
            "notifications", cli)
        text = inline.render_comment([overlay], repo="example-owner/c4spec", run_id=42, sha=SHA)
        heading = next(line for line in text.splitlines() if line.startswith("**＠reviewer"))
        self.assertNotIn("@reviewer", text)
        self.assertIn("＠reviewer", heading)
        self.assertIn("\\[click\\]", heading)
        self.assertNotIn("[click](", heading)
        self.assertIn("\\*bold\\*", heading)
        self.assertIn("\\`code\\`", heading)
        self.assertNotIn("<b>", text)
        self.assertIn("\\<b\\>", heading)

    def test_view_id_with_backtick_cannot_close_the_code_span(self):
        self.assertEqual(inline._code_span("a`b"), "``a`b``")
        self.assertEqual(inline._code_span("notifications"), "`notifications`")

    def test_render_refuses_too_many_views(self):
        with self.assertRaisesRegex(inline.UnsupportedFixture, "views"):
            inline.render_comment([self.overlay()] * (inline.MAX_VIEWS + 1),
                                  repo="example-owner/c4spec", run_id=42, sha=SHA)

    def test_render_rejects_invalid_identity(self):
        with self.assertRaisesRegex(ValueError, "source"):
            inline.render_comment([self.overlay()], repo="example-owner/c4spec", run_id=42, sha="nope")


if __name__ == "__main__":
    unittest.main()
