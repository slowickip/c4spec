#!/usr/bin/env python3
"""Create an Actions rehearsal summary from native LikeC4 diff-list JSON.

No GitHub/network calls. The result is an advisory reviewer aid, not approval.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ARTIFACT = "native-diff-as-is-changes-to-be"


def cell(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()[:140]
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("|", "\\|")
            .replace(chr(96), "ʼ").replace("__TICK__", "ʼ")
            .replace("[", "\\[").replace("]", "\\]")
            .replace("@", "＠"))


def metric(view: dict, kind: str, action: str) -> int:
    value = view.get(kind, {}).get(action, 0)
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid LikeC4 metric: {kind}.{action}")
    return value


def validate_identity(repo: str, run_id: int, sha: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository")
    if type(run_id) is not int or run_id <= 0 or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Invalid source commit or run")


def render_comment(diffs: object, summary: dict, *, repo: str, run_id: int, sha: str,
                   inline: str | None = None) -> str:
    validate_identity(repo, run_id, sha)
    if not isinstance(diffs, list) or not isinstance(summary, dict):
        raise ValueError("Invalid native diff evidence")
    if summary.get("likec4Version") != "1.61.0":
        raise ValueError("Expected pinned LikeC4 1.61.0")
    required = ("validatedProposal", "dryRunNonMutating", "appliedAndValidated",
                "staleRemovalRejected", "overlappingDiffRejected", "modelOnlySourcePreserved")
    if any(summary.get(k) is not True for k in required):
        raise ValueError("Missing positive rehearsal evidence")
    name = summary.get("diff")
    matches = [d for d in diffs if isinstance(d, dict) and d.get("id") == name]
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching diff in native CLI output")
    diff = matches[0]
    if not isinstance(diff.get("views"), list):
        raise ValueError("No native impacted views")
    rows = []
    for v in diff["views"]:
        if not isinstance(v, dict):
            raise ValueError("Invalid native view record")
        ns = [metric(v, "nodes", a) for a in ("added", "removed", "modified")]
        es = [metric(v, "edges", a) for a in ("added", "removed", "modified")]
        if not any(ns + es):
            continue
        rows.append(
            f"| {cell(v.get('title', v.get('id', 'unknown')))} "
            f"(__TICK__{cell(v.get('id', 'unknown'))}__TICK__) | "
            f"+{ns[0]} / −{ns[1]} / ~{ns[2]} | "
            f"+{es[0]} / −{es[1]} / ~{es[2]} |"
        )
    if not rows or len(rows) > 40:
        raise ValueError("No affected view or too many affected views")
    title = cell(diff.get("title", name))
    description = diff.get("description", {})
    reason = cell(description.get("txt", "")) if isinstance(description, dict) else ""
    link = f"https://github.com/{repo}/actions/runs/{run_id}#artifacts"
    body = [
        "### Notification worker replacement",
        "",
        "This example exercises the pinned compiler on the online shop model.",
        "",
        f"**{title}** (__TICK__{cell(name)}__TICK__)",
        f"Intent: {reason}" if reason else "Intent: see proposal source",
        "",
        f"**Tool commit under test:** __TICK__{sha}__TICK__ · **LikeC4:** 1.61.0 · "
        f"**[Interactive comparison artifact]({link})**",
        "",
        "**Native LikeC4 per-view impact** (added / removed / modified):",
        "",
        "| View | Nodes (+ / − / ~) | Edges (+ / − / ~) |",
        "| --- | ---: | ---: |",
        *rows,
        "",
        "The table includes effective view changes, including edges removed"
        " by a deleted node; global relation counts may include only explicit removals.",
        "",
        f"**Review:** Open the CI run, download __TICK__{ARTIFACT}__TICK__,"
        " extract it and open __TICK__review-site/index.html__TICK__ locally."
        f" Select __TICK__{cell(name)}__TICK__ → **Changes** to see red removals,"
        " green additions and orange modifications. Compare **As-is / Changes / To-be**.",
        "",
        "**Verification:** Native validate/list/dry-run/apply, source preservation,"
        " stale removal and overlap rejection passed in a disposable fixture.",
        "",
        "Use the project PR for human design approval. The example artifact expires after 7 days.",
        "",
    ]
    if inline:
        # Generated Mermaid overlay, inserted where the reviewer starts looking.
        anchor = next((i for i, line in enumerate(body) if line.startswith("**Review:**")), None)
        if anchor is None:
            raise ValueError("Missing review-section anchor for the inline overlay")
        body[anchor:anchor] = [inline.strip(), ""]
    return "\n".join(body).replace("__TICK__", chr(96))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diff-list", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--inline-section", type=Path,
                   help="generated Mermaid overlay spliced into the note")
    a = p.parse_args()
    diffs = json.loads(a.diff_list.read_text(encoding="utf-8"))
    summary = json.loads(a.summary.read_text(encoding="utf-8"))
    inline = a.inline_section.read_text(encoding="utf-8") if a.inline_section else None
    note = render_comment(diffs, summary, repo=a.repo, run_id=a.run_id, sha=a.sha, inline=inline)
    print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
