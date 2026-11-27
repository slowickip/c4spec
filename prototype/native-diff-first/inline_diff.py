#!/usr/bin/env python3
"""Render a bounded GitHub-inline Mermaid overlay for a native LikeC4 diff.

Input is machine-readable LikeC4 output only: two
``likec4 export json --skip-layout`` documents (the proposal model = As-is and
a scratch ``likec4 diff apply`` copy = To-be) plus the official
``likec4 diff list --json`` record for the named diff. Nothing here is a second
architecture source; the ``.c4`` model stays authoritative.

The overlay is derived, not inferred from counts: node and edge identity are
matched across the two exported view graphs, and the per-view added / removed /
modified totals must equal the numbers LikeC4 itself reports for that diff.
A mismatch is a hard error, so the comment can never contradict the CLI.

Output is a single fenced ``mermaid`` block per selected view inside a Markdown
comment body. It is generated, advisory evidence, not approval.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MARKER = "<!-- c4spec-native-likec4-inline-diff -->"
MAX_VIEWS = 2
MAX_NODES = 40
MAX_EDGES = 80
MAX_BLOCK_CHARS = 20000


class UnsupportedFixture(ValueError):
    """The exported model cannot be rendered faithfully; refuse instead of guessing."""


@dataclass
class Overlay:
    view_id: str
    title: str
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    children: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class OutlineStyle:
    node_colors: dict[str, tuple[str, str, str]]
    edge_styles: dict[str, str]
    direction: str


def _text(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("txt", "")
    return "" if value is None else str(value)


def _node_signature(node: dict) -> tuple:
    return (
        node.get("title"), node.get("kind"), node.get("notation"),
        tuple(node.get("tags") or ()), _text(node.get("description")),
        node.get("shape"), node.get("color"),
    )


def _edge_signature(edge: dict) -> tuple:
    return (
        edge.get("label"), edge.get("line"), edge.get("head"),
        edge.get("color"), _text(edge.get("description")),
    )


def _uniform(edges: list[dict]) -> bool:
    """True when every edge is indistinguishable, so pairing order cannot matter."""
    return len({_edge_signature(edge) for edge in edges}) == 1


def view_of(document: dict, view_id: str) -> dict:
    views = document.get("views")
    if not isinstance(views, dict) or view_id not in views:
        raise UnsupportedFixture(f"view {view_id!r} is absent from the exported model")
    view = views[view_id]
    if not isinstance(view, dict) or view.get("_type") != "element":
        raise UnsupportedFixture(f"view {view_id!r} is not an element view")
    if not isinstance(view.get("nodes"), list) or not isinstance(view.get("edges"), list):
        raise UnsupportedFixture(f"view {view_id!r} has no computed nodes/edges")
    return view


def classify(asis_view: dict, tobe_view: dict) -> tuple[list[dict], list[dict], dict]:
    """Match nodes and edges across the two exported view graphs."""
    asis_nodes = {n["id"]: n for n in asis_view["nodes"]}
    tobe_nodes = {n["id"]: n for n in tobe_view["nodes"]}
    nodes: dict[str, dict] = {}
    # As-is order first so the diagram reads like the current model; a modified
    # node is labelled with its proposed (To-be) properties.
    for node_id in [*asis_nodes, *(i for i in tobe_nodes if i not in asis_nodes)]:
        if node_id in tobe_nodes and node_id in asis_nodes:
            state = ("unchanged" if _node_signature(asis_nodes[node_id]) == _node_signature(tobe_nodes[node_id])
                     else "modified")
            nodes[node_id] = {**tobe_nodes[node_id], "state": state}
        elif node_id in asis_nodes:
            nodes[node_id] = {**asis_nodes[node_id], "state": "removed"}
        else:
            nodes[node_id] = {**tobe_nodes[node_id], "state": "added"}

    def grouped(view: dict) -> dict[tuple[str, str], list[dict]]:
        groups: dict[tuple[str, str], list[dict]] = {}
        for edge in view["edges"]:
            groups.setdefault((edge["source"], edge["target"]), []).append(edge)
        return groups

    asis_edges, tobe_edges = grouped(asis_view), grouped(tobe_view)
    edges: list[dict] = []
    for key in sorted(set(asis_edges) | set(tobe_edges)):
        left = list(asis_edges.get(key, []))
        right = list(tobe_edges.get(key, []))
        # Same endpoints and same label first: an exact match, or a modified one.
        for edge in list(left):
            match = next((c for c in right if c.get("label") == edge.get("label")), None)
            if match is None:
                continue
            state = "unchanged" if _edge_signature(edge) == _edge_signature(match) else "modified"
            edges.append({**match, "state": state, "asis_id": edge["id"]})
            left.remove(edge)
            right.remove(match)
        # Remaining edges on the same endpoints are the same connection with a
        # new label: LikeC4 reports those as modified, not added plus removed.
        if left and right:
            if len(left) == 1 and len(right) == 1:
                rematches = [(left[0], right[0])]
            elif _uniform(left) and _uniform(right):
                # Indistinguishable duplicates: every pairing renders the same.
                rematches = list(zip(left, right))
            else:
                # Two or more distinct candidates on both sides: the provider
                # reports only totals, so any pairing would be invented evidence.
                raise UnsupportedFixture(
                    f"ambiguous parallel relationships {key[0]!r} -> {key[1]!r}: "
                    f"{len(left)} unmatched As-is / {len(right)} unmatched To-be edges"
                )
            for edge, match in rematches:
                edges.append({**match, "state": "modified", "asis_id": edge["id"]})
                left.remove(edge)
                right.remove(match)
        edges.extend({**edge, "state": "removed"} for edge in left)
        edges.extend({**edge, "state": "added"} for edge in right)

    counts = {
        "nodes": {k: sum(1 for n in nodes.values() if n["state"] == k)
                  for k in ("added", "removed", "modified")},
        "edges": {k: sum(1 for e in edges if e["state"] == k)
                  for k in ("added", "removed", "modified")},
    }
    return list(nodes.values()), edges, counts


def _checked_children(nodes: list[dict], children: dict[str, list[str]]) -> tuple[dict[str, list[str]], list[str]]:
    """Validate containment before emitting anything.

    A node whose parent differs between As-is and To-be would otherwise be
    emitted under two subgraphs with one Mermaid id, and a cycle would silently
    produce a diagram with no roots and therefore no nodes. Both are refused:
    the native HTML stays the comparison instead of a best-effort graph.
    """
    order = [node["id"] for node in nodes]
    known = set(order)
    kids = {node_id: [c for c in children.get(node_id, []) if c in known] for node_id in order}
    parents: dict[str, str] = {}
    for parent_id, members in kids.items():
        for child in members:
            if child in parents and parents[child] != parent_id:
                raise UnsupportedFixture(
                    f"contradictory containment: {child!r} is a child of "
                    f"{parents[child]!r} and {parent_id!r}"
                )
            parents[child] = parent_id
    for node_id in order:
        seen: set[str] = set()
        current = node_id
        while current in parents:
            if current in seen:
                raise UnsupportedFixture(f"cyclic containment through {current!r}")
            seen.add(current)
            current = parents[current]
    roots = [node_id for node_id in order if node_id not in parents]
    if not roots:
        raise UnsupportedFixture("containment has no root element")
    return kids, roots


def build_overlay(asis_doc: dict, tobe_doc: dict, view_id: str, cli_view: dict) -> Overlay:
    reported = {
        "nodes": {k: int(cli_view.get("nodes", {}).get(k, 0)) for k in ("added", "removed", "modified")},
        "edges": {k: int(cli_view.get("edges", {}).get(k, 0)) for k in ("added", "removed", "modified")},
    }
    return build_view_overlay(view_of(asis_doc, view_id), view_of(tobe_doc, view_id),
                              view_id, str(cli_view.get("title") or view_id), reported=reported)


def build_view_overlay(asis: dict, tobe: dict, view_id: str, title: str, *,
                       reported: dict | None = None) -> Overlay:
    nodes, edges, counts = classify(asis, tobe)
    if reported is not None and counts != reported:
        raise UnsupportedFixture(
            f"{view_id}: derived deltas {counts} disagree with LikeC4 {reported}"
        )
    if not any(counts["nodes"].values()) and not any(counts["edges"].values()):
        raise UnsupportedFixture(f"{view_id}: no visible change to overlay")
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise UnsupportedFixture(
            f"{view_id}: {len(nodes)} nodes / {len(edges)} edges exceed the inline bound"
        )
    # Nesting must survive the diff: a removed child and its added replacement
    # both belong to the same container, so union the two children lists — then
    # reject any hierarchy the union cannot represent unambiguously.
    known = {node["id"] for node in nodes}
    children: dict[str, list[str]] = {node_id: [] for node_id in known}
    for view in (asis, tobe):
        for node in view["nodes"]:
            for child in node.get("children") or []:
                if node["id"] in known and child in known and child not in children[node["id"]]:
                    children[node["id"]].append(child)
    children, _ = _checked_children(nodes, children)
    return Overlay(view_id=view_id, title=title, nodes=nodes, edges=edges, counts=counts,
                   children=children)


def _label(value: object) -> str:
    """One-line, markup-neutral Mermaid label."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace('"', "&quot;").replace("`", "'").replace("|", "&#124;")
    return text[:120]


def render_overlay(overlay: Overlay, *, outline: OutlineStyle | None = None) -> str:
    order = {node["id"]: f"n{i}" for i, node in enumerate(overlay.nodes)}
    by_id = {node["id"]: node for node in overlay.nodes}
    children, roots = _checked_children(overlay.nodes, overlay.children)
    lines = [f"flowchart {outline.direction if outline else 'TB'}"]
    changed_boxes: list[tuple[str, str]] = []
    node_styles: list[str] = []
    if outline is None:
        accents = {"added": "#16a34a", "removed": "#dc2626", "modified": "#ea580c"}
    else:
        accents = {"added": "#3fb950", "removed": "#f85149", "modified": "#ea580c"}
    signs = {"added": "+", "removed": "−", "modified": "~"}

    def change_style(state: str) -> list[str]:
        if state not in accents:
            return []
        result = [f"stroke:{accents[state]}", "stroke-width:3px"]
        if state == "removed":
            result.append("stroke-dasharray:5 3")
        return result

    def emit(node_id: str, depth: int) -> None:
        node = by_id[node_id]
        state = node["state"]
        pad = "  " * (depth + 1)
        label = _label(node.get("title", node_id))
        if outline and state in signs:
            label = f"{signs[state]} {label}"
        kids = children.get(node_id, [])
        name = order[node_id]
        if kids:
            lines.append(f'{pad}subgraph {name}["{label}"]')
            for child in kids:
                emit(child, depth + 1)
            lines.append(f"{pad}end")
            if state != "unchanged":
                changed_boxes.append((name, state))
        elif outline is None:
            lines.append(f'{pad}{name}["{label}"]:::{state}')
        else:
            lines.append(f'{pad}{name}["{label}"]')
            styles = []
            if node_id in outline.node_colors:
                fill, stroke, color = outline.node_colors[node_id]
                styles.extend((f"fill:{fill}", f"color:{color}"))
                if state == "unchanged":
                    styles.append(f"stroke:{stroke}")
            styles.extend(change_style(state))
            if styles:
                node_styles.append(f"  style {name} {','.join(styles)}")

    for node_id in roots:
        emit(node_id, 0)

    styles: dict[str, list[int]] = {"added": [], "removed": [], "modified": []}
    for index, edge in enumerate(overlay.edges):
        state = edge["state"]
        dashed = edge.get("line") == "dashed" or (outline and state == "removed")
        arrow = "-.->" if dashed else "-->"
        label = _label(edge["label"]) if edge.get("label") else ""
        if outline and state in signs:
            label = f"{signs[state]} {label}".strip()
        text = f'|"{label}"|' if label else ""
        lines.append(f"  {order[edge['source']]} {arrow}{text} {order[edge['target']]}")
        if state != "unchanged":
            styles[state].append(index)

    if outline is None:
        lines += [
            "  classDef unchanged fill:#f8fafc,stroke:#94a3b8,color:#0f172a",
            "  classDef added fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d",
            "  classDef removed fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d,stroke-dasharray:5 3",
            "  classDef modified fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#7c2d12",
        ]
    lines.extend(node_styles)
    for box_id, state in changed_boxes:
        # Mermaid uses the active theme's text color for cluster labels.
        stroke = change_style(state) if outline else [f"stroke:{accents[state]}", "stroke-width:2px"]
        lines.append(f"  style {box_id} fill:transparent,{','.join(stroke)}")
    # Neutral containers, matching the un-diffed export instead of Mermaid's
    # default cluster accent.
    changed_ids = {box_id for box_id, _ in changed_boxes}
    for node_id in order:
        if children.get(node_id) and order[node_id] not in changed_ids:
            lines.append(f"  style {order[node_id]} fill:transparent,stroke:#94a3b8")
    if outline:
        for index, edge in enumerate(overlay.edges):
            if edge["state"] == "unchanged" and edge["id"] in outline.edge_styles:
                lines.append(f"  linkStyle {index} {outline.edge_styles[edge['id']]}")
    for state, color in accents.items():
        if styles[state]:
            indexes = ",".join(str(i) for i in styles[state])
            stroke = change_style(state) if outline else [f"stroke:{color}", "stroke-width:2px"]
            lines.append(f"  linkStyle {indexes} {','.join(stroke)}")
    return "\n".join(lines)


def escape_heading(value: object) -> str:
    """One-line Markdown label for prose outside a Mermaid fence.

    Provider text must not be able to mention a user, open a link, or start
    emphasis/code formatting in the bot comment, so markdown-active characters
    are backslash-escaped and ``@`` is swapped for a look-alike.
    """
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = text.replace("\\", "\\\\")
    for char in ("`", "*", "_", "~", "|", "[", "]", "<", ">", "#"):
        text = text.replace(char, "\\" + char)
    text = text.replace("&", "&amp;").replace("@", "＠")
    return text[:160]


def _code_span(value: object) -> str:
    """Inline code that a backtick in provider data cannot terminate."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return f"``{text}``" if "`" in text else f"`{text}`"


def render_comment(overlays: list[Overlay], *, repo: str, run_id: int, sha: str,
                   artifact: str | None = None) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository")
    if type(run_id) is not int or run_id <= 0 or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Invalid source commit or run")
    if not 1 <= len(overlays) <= MAX_VIEWS:
        raise UnsupportedFixture(f"expected 1-{MAX_VIEWS} views, got {len(overlays)}")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    parts = [
        MARKER,
        "### Inline native LikeC4 diff — generated, advisory, not approved",
        "",
        f"**Source commit:** `{sha}` · **LikeC4:** 1.61.0 · **[CI run]({run_url})**"
        + (f" · **[full interactive artifact]({run_url}#artifacts)** (`{artifact}`)" if artifact else ""),
        "",
        "Derived from the `.c4` model only: `export json` of the proposal (As-is) and of a",
        "scratch `diff apply` copy (To-be). Per-view counts below are LikeC4's own; the",
        "overlay is red = removed, green = added, orange = modified. Nothing is committed.",
        "",
        f"Red/green is a derived *view*, the `.c4` diff and its native rendering stay canonical.",
        "",
    ]
    for overlay in overlays:
        counts = overlay.counts
        block = render_overlay(overlay)
        if len(block) > MAX_BLOCK_CHARS:
            raise UnsupportedFixture(f"{overlay.view_id}: Mermaid block exceeds the inline bound")
        parts += [
            f"**{escape_heading(overlay.title)}** ({_code_span(overlay.view_id)}) — nodes "
            f"+{counts['nodes']['added']} / −{counts['nodes']['removed']} / ~{counts['nodes']['modified']}, "
            f"edges +{counts['edges']['added']} / −{counts['edges']['removed']} / ~{counts['edges']['modified']}",
            "",
            "```mermaid",
            block,
            "```",
            "",
        ]
    parts += [
        "**Verification:** native validate/list/dry-run/apply passed for this diff; the derived",
        "deltas match LikeC4's reported per-view impact exactly, including effective edges",
        "removed with a deleted node.",
        "",
        "**Scope:** teaching fixture, not a production change, deployment or design approval.",
    ]
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asis-json", type=Path, required=True)
    parser.add_argument("--tobe-json", type=Path, required=True)
    parser.add_argument("--diff-list", type=Path, required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--view", action="append", default=[])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--artifact")
    args = parser.parse_args()

    asis = json.loads(args.asis_json.read_text(encoding="utf-8"))
    tobe = json.loads(args.tobe_json.read_text(encoding="utf-8"))
    listed = json.loads(args.diff_list.read_text(encoding="utf-8"))
    matches = [d for d in listed if isinstance(d, dict) and d.get("id") == args.diff]
    if len(matches) != 1:
        raise SystemExit("error: expected exactly one matching native diff")
    views = {v["id"]: v for v in matches[0].get("views") or [] if isinstance(v, dict)}
    affected = [v for v in views.values() if any(v.get("nodes", {}).values())
                or any(v.get("edges", {}).values())]
    # Prefer views where the topology itself changes; edge-only aggregate views
    # (landscape roll-ups) are the least informative and get the spare slot.
    ranked = sorted(affected, key=lambda v: (-sum(v.get("nodes", {}).values()),
                                             -sum(v.get("edges", {}).values())))
    selected = args.view or [v["id"] for v in ranked[:MAX_VIEWS]]
    if len(selected) > MAX_VIEWS:
        raise SystemExit(f"error: at most {MAX_VIEWS} views may be rendered inline")
    overlays = [build_overlay(asis, tobe, view_id, views[view_id]) for view_id in selected]
    print(render_comment(overlays, repo=args.repo, run_id=args.run_id, sha=args.sha,
                         artifact=args.artifact), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
