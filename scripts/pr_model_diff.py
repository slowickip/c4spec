"""Prepare a GitHub comment from changed diagrams in committed LikeC4 projects."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/c4spec/scripts"))
sys.path.insert(0, str(ROOT / "prototype/native-diff-first"))
from diff import select_project
from inline_diff import (
    MAX_EDGES, OutlineStyle, Overlay, UnsupportedFixture, build_view_overlay, escape_heading, render_overlay,
)

# Keep the existing marker so the publisher replaces or clears old comments.
MARKER = "<!-- c4spec-native-likec4-diff-review -->"
MAX_COMMENT_BYTES = 60_000
HEX = r"#[0-9a-fA-F]{3,8}"
NODE_STYLE = re.compile(rf"(?m)^ +classDef (\w+) fill:({HEX}),stroke:({HEX}),color:({HEX})$")
EDGE_STYLE = re.compile(rf"(?m)^ +linkStyle (\d+(?:,\d+)*) (stroke:{HEX}(?:,stroke-dasharray:[\d ]+)?)$")
MERMAID_FENCE = re.compile(r"^(`{3,})mermaid\n(.*?)^\1\n", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True)
class Diagram:
    mermaid: str
    view: dict


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "--literal-pathspecs", *args])


def snapshot(revision: str, model_dir: str, destination: Path) -> Path | None:
    if not git("ls-tree", revision, "--", model_dir):
        return None
    with tarfile.open(fileobj=io.BytesIO(git("archive", revision, "--", model_dir))) as archive:
        if any(not (entry.isfile() or entry.isdir()) for entry in archive.getmembers()):
            raise ValueError(f"Only regular files may be rendered in {model_dir}")
        archive.extractall(destination, filter="data")
    model = destination / model_dir
    return model if any(
        file.is_file() and file.suffix.lower() in {".c4", ".likec4"}
        for file in model.rglob("*")
    ) else None


def compile_model(compiler: Path, model: Path, *args: str) -> str:
    return subprocess.check_output([str(compiler), *args], cwd=model, text=True)


def diagrams(compiler: Path, model: Path, output: Path) -> dict[str, Diagram]:
    output.mkdir(parents=True)
    compile_model(compiler, model, "gen", "mermaid", "-o", str(output), ".")
    export = output / "computed.json"
    compile_model(compiler, model, "export", "json", "--skip-layout", "-o", str(export), ".")
    views = select_project(json.loads(export.read_text(encoding="utf-8")))["views"]
    return {
        path.stem: Diagram(path.read_text(encoding="utf-8").strip(), views[path.stem])
        for path in sorted(output.rglob("*.mmd"))
    }


def diagram_states(compiler: Path, model: Path | None, output: Path):
    if model is None:
        return {}, {}
    compile_model(compiler, model, "validate", "--json", "--no-layout", ".")
    current = diagrams(compiler, model, output / "current")
    proposals = {}
    for index, diff in enumerate(json.loads(compile_model(compiler, model, "diff", "list", "--json", "."))):
        name = diff["id"]
        if name.startswith("-") or name in proposals:
            raise ValueError(f"Invalid or duplicate native diff {name!r}")
        scratch = output / f"diff-{index}"
        applied = scratch / "model"
        shutil.copytree(model, applied)
        # Each proposal is applied independently to a scratch copy.
        compile_model(compiler, applied, "diff", "apply", name, ".")
        compile_model(compiler, applied, "validate", "--json", "--no-layout", ".")
        proposals[name] = diagrams(compiler, applied, scratch / "diagrams")
    return current, proposals


def mermaid_block(source: str) -> str:
    longest = max((len(match.group()) for match in re.finditer(r"`+", source)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}mermaid\n{source}\n{fence}\n"


def node_colors(diagram: Diagram | None) -> dict[str, tuple[str, str, str]]:
    if diagram is None:
        return {}
    nodes = [node for node in diagram.view["nodes"] if not node["children"] and node.get("shape") != "person"]
    colors = list(dict.fromkeys(node["color"] for node in nodes))
    definitions = NODE_STYLE.findall(diagram.mermaid)
    if len(colors) != len(definitions):
        raise UnsupportedFixture("Mermaid color definitions do not match the computed view")
    palette = {}
    # LikeC4 emits classes in first occurrence order. Verify the class name
    # too, including the suffixes it uses for sanitized-name collisions.
    for token, (name, fill, stroke, text) in zip(colors, definitions):
        base = re.sub(r"\W", "_", token, flags=re.ASCII)
        if not re.fullmatch(rf"{re.escape(base)}(?:_\d+)?", name):
            raise UnsupportedFixture(f"Unexpected Mermaid color class {name!r}")
        palette[token] = fill, stroke, text
    return {node["id"]: palette[node["color"]] for node in nodes}


def outlined_diagram(overlay: Overlay, before: Diagram | None, after: Diagram | None) -> str:
    displayed = after or before
    edges = displayed.view["edges"]
    edge_styles = {
        edges[int(index)]["id"]: style
        for indexes, style in EDGE_STYLE.findall(displayed.mermaid)
        for index in indexes.split(",")
        if int(index) < len(edges)
    }
    direction = displayed.view.get("autoLayout", {}).get("direction")
    theme = OutlineStyle(
        node_colors={**node_colors(before), **node_colors(after)},
        edge_styles=edge_styles,
        direction=direction if direction in {"TB", "BT", "LR", "RL"} else "TB",
    )
    return mermaid_block(render_overlay(overlay, outline=theme))


def whole_view_change(diagram: Diagram, view_id: str, title: str, *, added: bool) -> str:
    label = "Added" if added else "Removed"
    if diagram.view.get("_type") == "element":
        empty = {"nodes": [], "edges": []}
        before, after = (empty, diagram.view) if added else (diagram.view, empty)
        try:
            overlay = build_view_overlay(before, after, view_id, title)
            rendered = outlined_diagram(overlay, None if added else diagram, diagram if added else None)
        except UnsupportedFixture:
            pass
        else:
            return f"**{label} · {title}**\n\n" + rendered
    indicator = "🟩" if added else "🟥"
    return f"{indicator} **{label} · {title}**\n\n" + mermaid_block(diagram.mermaid)


def diagram_overlay(before: Diagram, after: Diagram, view_id: str, title: str) -> Overlay:
    def visible_graph(diagram: Diagram) -> dict[str, list[dict]]:
        # LikeC4's Mermaid export omits descriptions from nodes and edges.
        return {key: [{k: v for k, v in item.items() if k != "description"}
                      for item in diagram.view[key]] for key in ("nodes", "edges")}

    old_view = visible_graph(before)
    overlay = build_view_overlay(old_view, visible_graph(after), view_id, title)
    if overlay.counts["nodes"]["modified"]:
        raise UnsupportedFixture("The overlay cannot show both versions of a modified node")

    old_edges = {edge["id"]: edge for edge in old_view["edges"]}
    edges = []
    for edge in overlay.edges:
        if edge["state"] != "modified":
            edges.append(edge)
            continue
        old = old_edges[edge["asis_id"]]
        if old.get("label") == edge.get("label") or any(
            old.get(key) != edge.get(key) for key in ("parent", "line", "head", "tail", "color")
        ):
            raise UnsupportedFixture("The overlay cannot show both styles of a modified relationship")
        edges.extend(({**old, "state": "removed"}, {**edge, "state": "added"}))
    if len(edges) > MAX_EDGES:
        raise UnsupportedFixture("The relationship labels exceed the inline edge bound")
    # Keep the semantic counts from the match. The red/green pair is a display
    # of the edit to one relationship.
    return replace(overlay, edges=edges)


def diagram_change(before: Diagram | None, after: Diagram | None, view_id: str, title: str) -> str:
    if before is None:
        return whole_view_change(after, view_id, title, added=True)
    if after is None:
        return whole_view_change(before, view_id, title, added=False)
    if before.mermaid == after.mermaid:
        return ""
    if (before.view.get("_type") == after.view.get("_type") == "element" and
            before.view.get("title") == after.view.get("title") and
            before.view.get("autoLayout") == after.view.get("autoLayout")):
        try:
            overlay = diagram_overlay(before, after, view_id, title)
            states = {item["state"] for item in (*overlay.nodes, *overlay.edges)}
            legend = " · ".join(
                label for state, label in (
                    ("added", "+ Green outlines show additions"), ("removed", "− Red dashed outlines show removals"),
                )
                if state in states
            )
            return f"**{title}** · {legend}\n\n" + outlined_diagram(overlay, before, after)
        except UnsupportedFixture:
            pass
    return (f"**{title} · Before**\n\n" + mermaid_block(before.mermaid) +
            f"\n**{title} · After**\n\n" + mermaid_block(after.mermaid))


def changes(before: dict[str, Diagram], after: dict[str, Diagram], *, label: str = "") -> list[str]:
    blocks = []
    for view_id in sorted(before.keys() | after.keys()):
        left, right = before.get(view_id), after.get(view_id)
        title = escape_heading((right or left).view.get("title") or view_id)
        if label:
            title = f"{title} · {escape_heading(label)}"
        block = diagram_change(left, right, view_id, title)
        if block:
            blocks.append(block)
    return blocks


def compare(compiler: Path, base: str, head: str, model_dirs: list[str], scratch: Path) -> list[str]:
    blocks = []
    for index, model_dir in enumerate(model_dirs):
        if not git("diff", "--name-only", "-z", base, head, "--", model_dir):
            continue
        work = scratch / str(index)
        before, before_diffs = diagram_states(
            compiler, snapshot(base, model_dir, work / "base"), work / "base-views",
        )
        after, after_diffs = diagram_states(
            compiler, snapshot(head, model_dir, work / "head"), work / "head-views",
        )
        blocks.extend(changes(before, after))
        for name in sorted(before_diffs.keys() | after_diffs.keys()):
            blocks.extend(changes(before_diffs.get(name, after), after_diffs.get(name, after),
                                  label=f"Proposal {name}"))
    return blocks


def render_comment(blocks: list[str], *, repo: str, run_id: int, merge_base: str, head: str) -> tuple[str, str]:
    if not blocks:
        return "", ""
    header = f"{MARKER}\n### LikeC4 diagram changes\n\nMerge base: `{merge_base}` · PR head: `{head}`\n\n"
    full = header + "\n".join(blocks)
    link = f"[Download rendered diagrams](https://github.com/{repo}/actions/runs/{run_id}#artifacts)\n\n"
    comment = header + link
    for block in blocks:
        candidate = comment + block + "\n"
        if len(candidate.encode("utf-8")) <= MAX_COMMENT_BYTES:
            comment = candidate
    return comment, full


def write_png_inputs(document: str, output: Path) -> None:
    # Mermaid CLI's Markdown reader skips fences longer than three backticks.
    # Render each exact source as Mermaid and generate an index of static images.
    names = []

    def write_diagram(match: re.Match[str]) -> str:
        name = f"diagram-{len(names) + 1}"
        names.append(name)
        (output / f"{name}.mmd").write_text(match[2], encoding="utf-8")
        return f"![Diagram {len(names)}](./{name}.png)\n"

    index = MERMAID_FENCE.sub(write_diagram, document)
    (output / "diagrams.md").write_text(index, encoding="utf-8")
    (output / "diagram-names.txt").write_text("\n".join(names) + "\n", encoding="utf-8")


def project_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) == "." or ".." in path.parts:
        raise argparse.ArgumentTypeError("Expected a repository-relative project directory")
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--model-dir", action="append", type=project_path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if not all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in (args.base, args.head)):
        raise ValueError("Expected full Git commit SHAs")
    merge_base = git("merge-base", args.base, args.head).decode().strip()
    compiler = args.compiler.resolve(strict=True)
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["dependencies"]["likec4"]
    if compile_model(compiler, Path.cwd(), "--version").strip() != version:
        raise ValueError(f"Expected LikeC4 {version}")
    with TemporaryDirectory(prefix="c4spec-pr-views-") as directory:
        blocks = compare(compiler, merge_base, args.head, args.model_dir or ["architecture"], Path(directory))
    comment, full = render_comment(
        blocks, repo=args.repo, run_id=args.run_id, merge_base=merge_base, head=args.head,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    note = comment.encode("utf-8")
    (args.out / "comment.md").write_bytes(note)
    diagrams_path = args.out / "diagrams.md"
    if full:
        write_png_inputs(full, args.out)
    else:
        diagrams_path.unlink(missing_ok=True)
    (args.out / "metadata.json").write_text(json.dumps({
        "repo": args.repo,
        "pr": args.pr,
        "runId": args.run_id,
        "base": args.base,
        "head": args.head,
        "commentBytes": len(note),
    }), encoding="utf-8")


if __name__ == "__main__":
    main()
