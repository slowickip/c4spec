#!/usr/bin/env python3
"""Conservative semantic LikeC4 JSON comparison, not a replacement for source diff."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from provenance import (HEX40, git_toplevel, sha256_bytes, sha256_file,
                        validate_provenance, verify_sources_at_commit)

VIEW_KEYS = ("id", "title", "description", "_type", "flow", "viewOf", "variant", "tags", "metadata", "links", "rules", "notation", "nodes", "edges")
ELEMENT_KEYS = ("id", "kind", "title", "summary", "description", "technology", "tags", "metadata", "parent", "links")
ELEMENT_SUMMARY_KEYS = ("id", "kind", "title", "description", "technology", "parent")
REL_KEYS = ("source", "target", "kind", "title", "summary", "description", "technology", "tags", "metadata", "direction", "isBidirectional")
REL_IDENTITY_KEYS = ("source", "target", "kind", "direction", "isBidirectional")
SOURCE_BOUND_FORMAT = "c4spec-source-bound-review-v1"


def select_project(data, project_id=None):
    """Normalize 1.59/1.60 LikeC4 export shapes without silently dropping data.

    Shared by the diff and structural checker. Identical repeated records for
    one project are accepted; conflicting duplicates are never silently picked.
    """
    entries = data if isinstance(data, list) else [data]
    if not entries:
        raise ValueError("LikeC4 export contains no projects")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("projectId"), str) or not all(
                isinstance(entry.get(k), dict) for k in ("elements", "relations", "views")):
            raise ValueError("Expected computed LikeC4 project(s) with projectId, elements, relations and views")
    if project_id is not None:
        entries = [entry for entry in entries if entry["projectId"] == project_id]
        if not entries:
            raise ValueError("Requested LikeC4 project was not found: " + project_id)
    projects = {entry["projectId"] for entry in entries}
    if len(projects) != 1:
        raise ValueError("Export contains multiple project IDs; specify --project explicitly")
    first = entries[0]
    if any(canon(entry) != canon(first) for entry in entries[1:]):
        raise ValueError("Conflicting duplicate LikeC4 project entries; refusing to discard changes")
    return first


def load(path, project_id=None):
    """Read JSON from disk and select a computed LikeC4 project."""
    return select_project(json.loads(Path(path).read_text(encoding="utf-8")), project_id)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def selected(data, keys):
    return {k: data[k] for k in keys if k in data}


def element_changes(base, head, keys, summary_keys=None):
    b = {k: selected(v, keys) for k, v in base.items()}
    h = {k: selected(v, keys) for k, v in head.items()}
    modified = sorted(x for x in set(h) & set(b) if canon(h[x]) != canon(b[x]))
    field_changes = {}
    for eid in modified:
        before, after = b[eid], h[eid]
        field_changes[eid] = {
            key: {"beforePresent": key in before, "afterPresent": key in after,
                  "before": before.get(key), "after": after.get(key)}
            for key in sorted(set(before) | set(after))
            if (key in before) != (key in after) or canon(before.get(key)) != canon(after.get(key))
        }
    result = {"added": sorted(set(h) - set(b)),
              "removed": sorted(set(b) - set(h)),
              "modified": modified, "fieldChanges": field_changes}
    if summary_keys is not None:
        # New C4 elements need names, responsibilities and technology in review,
        # not merely IDs. Include removed elements for symmetric comparison.
        result["addedDetails"] = {eid: selected(h[eid], summary_keys) for eid in result["added"]}
        result["removedDetails"] = {eid: selected(b[eid], summary_keys) for eid in result["removed"]}
    return result



def view_semantics(view, relation_lookup):
    """Keep view membership and flow semantics, but discard layout geometry.

    Adapted from the early C4Spec consumer prototype. Uses released LikeC4
    export fields.
    Source view selectors may still be omitted by LikeC4; compare raw .c4 too.
    """
    out = selected(view, tuple(k for k in VIEW_KEYS if k not in ("nodes", "edges", "flow")))
    nodes = view.get("nodes", [])
    edges = view.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Computed LikeC4 view nodes and edges must be lists")
    normalized_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("Computed LikeC4 view node must be an object")
        normalized_nodes.append({
            "id": node.get("id"), "modelRef": node.get("modelRef"),
            "parent": node.get("parent"),
            "children": sorted(node.get("children") or [], key=canon),
        })
    out["nodes"] = sorted(normalized_nodes, key=canon)

    edge_lookup = {}
    normalized_edges = []
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("id"), str):
            raise ValueError("Computed LikeC4 view edge must have an ID")
        eid = edge["id"]
        if eid in edge_lookup:
            raise ValueError("Computed LikeC4 view has duplicate edge IDs")
        normalized = selected(edge, ("source", "target", "title", "description", "technology", "kind", "direction"))
        refs = edge.get("relations") or []
        if not isinstance(refs, list):
            raise ValueError("Computed LikeC4 view edge relations must be a list")
        normalized["relations"] = []
        for rid in refs:
            if rid not in relation_lookup:
                raise ValueError("Computed LikeC4 view references missing model relation: " + str(rid))
            normalized["relations"].append(canon(selected(relation_lookup[rid], REL_KEYS)))
        normalized["relations"].sort()
        edge_lookup[eid] = normalized
        normalized_edges.append(normalized)
    out["edges"] = sorted(normalized_edges, key=canon)

    if "flow" in view:
        def resolve_flow(items):
            if not isinstance(items, list):
                raise ValueError("Computed LikeC4 dynamic flow must be a list")
            resolved = []
            for item in items:
                if isinstance(item, str):
                    # Preserve unresolved identifiers as an explicit limitation.
                    resolved.append(edge_lookup.get(item, {"unresolvedStep": item}))
                elif isinstance(item, dict) and "flow" in item:
                    subflow = selected(item, ("_type", "title", "description"))
                    subflow["flow"] = resolve_flow(item["flow"])
                    resolved.append(subflow)
                else:
                    raise ValueError("Unexpected dynamic flow item")
            return resolved
        out["flow"] = resolve_flow(view["flow"])
    return out

def relations(data):
    # Ignore generated relation IDs; preserve parallel edges via multiplicities.
    return Counter(canon(selected(r, REL_KEYS)) for r in data.values())


def relationship_changes(base, head):
    """Compare exact relations first; pair property edits only when unambiguous.

    A generated LikeC4 relation ID is not a durable identity. Two relations
    sharing source/target/kind may be independent parallel edges, so we never
    guess which one changed unless there is exactly ONE relation in that
    structural group on BOTH sides. Ambiguous parallels remain removed/added.
    """
    before, after = relations(base), relations(head)
    removed, added = before - after, after - before

    def by_identity(counter):
        groups = {}
        for serialized, count in counter.items():
            identity = canon(selected(json.loads(serialized), REL_IDENTITY_KEYS))
            groups.setdefault(identity, []).extend([serialized] * count)
        return groups

    bg, hg = by_identity(before), by_identity(after)
    modified = []
    for identity in sorted(set(bg) & set(hg)):
        if len(bg[identity]) != 1 or len(hg[identity]) != 1:
            continue
        old, new = bg[identity][0], hg[identity][0]
        if old == new:
            continue
        if removed[old] != 1 or added[new] != 1:
            continue
        before_rel, after_rel = json.loads(old), json.loads(new)
        fields = {
            key: {"beforePresent": key in before_rel, "afterPresent": key in after_rel,
                  "before": before_rel.get(key), "after": after_rel.get(key)}
            for key in sorted(set(before_rel) | set(after_rel))
            if (key in before_rel) != (key in after_rel)
            or canon(before_rel.get(key)) != canon(after_rel.get(key))
        }
        modified.append({"identity": json.loads(identity), "fieldChanges": fields})
        del removed[old]
        del added[new]
    return {
        "added": [{"relationship": json.loads(s), "count": n} for s, n in sorted(added.items())],
        "removed": [{"relationship": json.loads(s), "count": n} for s, n in sorted(removed.items())],
        "modified": modified,
    }


def semantic_snapshot(project):
    """Architecture-relevant data only, stable across layout-only changes."""
    return {
        "projectId": project.get("projectId"),
        "elements": {eid: selected(element, ELEMENT_KEYS)
                     for eid, element in project["elements"].items()},
        "relationships": sorted((value, count)
                                for value, count in relations(project["relations"]).items()),
        "views": {vid: view_semantics(view, project["relations"])
                  for vid, view in project["views"].items()},
    }


def load_provenance(path, label, expected_ref=None):
    """Read and fully validate a paired provenance artifact, failing closed."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as ex:
        raise ValueError("Cannot read " + label + " provenance: " + str(path)) from ex
    validate_provenance(document, label)
    if expected_ref is not None:
        if not HEX40.match(str(expected_ref)):
            raise ValueError(label + " ref must be a full 40-character lowercase SHA")
        if expected_ref != document["gitCommit"]:
            raise ValueError(label + " ref " + expected_ref + " does not match its provenance commit " + document["gitCommit"])
    return document


def load_change_record(path):
    """Hash the supplied change record bytes; schema validation stays in check.py."""
    try:
        raw = Path(path).read_bytes()
    except OSError as ex:
        raise ValueError("Cannot read change record: " + str(path)) from ex
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as ex:
        raise ValueError("Change record is not valid UTF-8 JSON") from ex
    if not isinstance(document, dict) or not isinstance(document.get("id"), str) or not document["id"]:
        raise ValueError("Change record must be a JSON object with a non-empty string id")
    return {"id": document["id"], "sha256": sha256_bytes(raw)}


def graph_delta(core):
    return (any(core["elements"][key] for key in ("added", "removed", "modified"))
            or any(core["relationships"][key] for key in ("added", "removed", "modified"))
            or any(core["views"][key] for key in ("added", "removed", "modified")))


def bound_summary(document):
    return {"gitCommit": document["gitCommit"], "compilerVersion": document["compilerVersion"],
            "compilerCommandReported": document["compilerCommandReported"],
            "modelDir": document["modelDir"], "sources": document["sources"],
            "sourcesDigest": document["sourcesDigest"], "export": document["export"]}


def assurance_level(review, base_doc, head_doc):
    """Separate caller-declared provenance from independently re-verified inputs."""
    git_reverified = review.get("gitReverified") is True
    compiler_reported = bool(base_doc["compilerCommandReported"] and head_doc["compilerCommandReported"])
    if git_reverified and compiler_reported:
        return "git-verified-compiler-reported", git_reverified, compiler_reported
    if git_reverified:
        return "git-verified", git_reverified, compiler_reported
    return "self-declared", git_reverified, compiler_reported


def review_fields(review, core, before, after, project_id):
    """Exploratory by default; a review fingerprint only when inputs are paired."""
    fields = {
        "reviewStatus": "exploratory",
        "reviewFingerprint": None,
        "reviewFingerprintScope": "unbound: no paired provenance, Git refs, compiler versions or change record are bound",
        "reviewBinding": None,
        "reviewAssurance": None,
        "reviewLimitations": [
            "An unbound comparison is exploratory: it reports the semantic delta but binds no source snapshot, commit, compiler version or change record",
            "No authenticated human approval in either mode",
        ],
        "humanApprovalVerified": False,
    }
    if review is None:
        return fields
    base_doc, head_doc = review["base"], review["head"]
    for label, document, export in (("base", base_doc, review["baseExport"]),
                                    ("head", head_doc, review["headExport"])):
        if sha256_file(export) != document["export"]["sha256"]:
            raise ValueError(label + " export bytes do not match its provenance digest (stale or altered export)")
        if document["export"]["projectId"] != project_id:
            raise ValueError(label + " provenance describes project " + document["export"]["projectId"]
                             + " but the export contains " + str(project_id))
    if base_doc["gitCommit"] == head_doc["gitCommit"]:
        raise ValueError("Paired provenance must name two different Git commits")
    if base_doc["sourcesDigest"] == head_doc["sourcesDigest"] and graph_delta(core):
        raise ValueError("Computed model changed but both source manifests are identical; the export has no source evidence")
    payload = {
        "format": SOURCE_BOUND_FORMAT,
        "diff": {"projectId": core["projectId"], "elements": core["elements"],
                 "relationships": core["relationships"], "views": core["views"]},
        "models": {"base": before, "head": after},
        "provenance": {"base": bound_summary(base_doc), "head": bound_summary(head_doc)},
        "change": review.get("change"),
    }
    level, git_reverified, compiler_reported = assurance_level(review, base_doc, head_doc)
    limitations = list(review.get("limitations", []))
    if not git_reverified:
        limitations.append("Git blobs were neither re-enumerated nor re-hashed here: manifest completeness and content are self-declared by the sidecars; pass --repo-root to prove them")
    if not compiler_reported:
        limitations.append("Compiler versions are caller-supplied strings; provenance.py records a command-output match only when --compiler-command was run, and even then the exporter is unverified")
    else:
        limitations.append("The compiler version is producer-reported command output (a sidecar boolean): it does not prove which LikeC4 binary produced this export")
    fields.update({
        "reviewStatus": "source-bound-self-declared" if level == "self-declared" else "source-bound-reverified",
        "reviewFingerprint": "sha256:" + hashlib.sha256(canon(payload).encode("utf-8")).hexdigest(),
        "reviewFingerprintScope": ("normalized semantic diff and both computed models + sorted .c4/config source manifests "
                                   "+ exact Git commits + LikeC4 compiler versions + export digests + optional change-record hash"),
        "reviewAssurance": {"level": level, "gitBlobsReverified": git_reverified,
                            "compilerVersionCommandReported": compiler_reported,
                            "exportBoundToCompiler": False,
                            "exportBytesRehashed": True, "humanApprovalVerified": False},
        "reviewBinding": {"base": bound_summary(base_doc), "head": bound_summary(head_doc),
                          "change": review.get("change"), "assurance": level,
                          "checks": list(review.get("checks", [])),
                          "humanApprovalVerified": False},
        "reviewLimitations": limitations + [
            "The review fingerprint binds inputs, not identity: it is not a signature and proves no human approval",
            "Source-bound means the compared bytes are known, not that the model or behaviour is correct",
            "Normalized snapshots exclude deployment blocks, layout and unexported source selectors; the source manifest still changes",
        ],
    })
    return fields


def compare(base, head, review=None):
    if base.get("projectId") != head.get("projectId"):
        raise ValueError("Cannot compare different LikeC4 projects")
    before, after = semantic_snapshot(base), semantic_snapshot(head)
    ec = element_changes(before["elements"], after["elements"], ELEMENT_KEYS, ELEMENT_SUMMARY_KEYS)
    vc = element_changes(before["views"], after["views"], VIEW_KEYS)
    rc = relationship_changes(base["relations"], head["relations"])
    core = {"projectId": base.get("projectId"), "elements": ec,
            "relationships": rc, "views": vc}
    # "index" is commonly LikeC4's computed landscape projection and may
    # change when elements change, even without a source edit to that view.
    # Keep it visible (a user could author their own view named "index").
    notes = []
    if "index" in set(vc["added"] + vc["modified"] + vc["removed"]):
        notes.append("The 'index' view may be generated by LikeC4; compare the raw .c4 source before treating it as an authored view edit")
    # Hash entire computed before/after states, NOT only locations or changed IDs.
    # It is an advisory checksum, not Git-bound/authenticated human approval.
    fingerprint_input = {"format": "c4spec-computed-graph-v2", "base": before, "head": after}
    result = {"schemaVersion": 1, **core,
              "reviewHints": notes,
              "fingerprint": "sha256:" + hashlib.sha256(canon(fingerprint_input).encode("utf-8")).hexdigest(),
              "fingerprintScope": "normalized base and head computed LikeC4 models; excludes layout and unexported source rules",
              "limitations": ["Review raw .c4 Git diff: original view selector rules may not appear in computed exports",
                              "Fingerprint is value-sensitive but is not signed or bound to Git SHA, policy, source selectors or reviewer identity",
                              "Renamed element IDs are shown as remove/add and must be reviewed manually",
                              "Parallel relationships are not automatically paired: ambiguous edits remain added/removed"]}
    result.update(review_fields(review, core, before, after, base.get("projectId")))
    return result


def build_review(args):
    """Assemble paired review inputs from CLI arguments, failing closed."""
    if bool(args.base_provenance) != bool(args.head_provenance):
        raise ValueError("Paired provenance is required: supply BOTH --base-provenance and --head-provenance")
    if args.change and not args.base_provenance:
        raise ValueError("--change requires paired provenance so its hash is bound into the review fingerprint")
    if (args.base_ref or args.head_ref) and not args.base_provenance:
        raise ValueError("--base-ref/--head-ref require paired provenance")
    if not args.base_provenance:
        return None
    base_doc = load_provenance(args.base_provenance, "base", args.base_ref)
    head_doc = load_provenance(args.head_provenance, "head", args.head_ref)
    checks = ["paired base/head provenance validated", "export bytes match the recorded digests"]
    limitations = []
    git_reverified = False
    if args.repo_root:
        toplevel = git_toplevel(Path(args.repo_root))
        for label, document in (("base", base_doc), ("head", head_doc)):
            verify_sources_at_commit(toplevel, document["modelDir"], document["sources"], document["gitCommit"])
        checks.append("source manifests re-enumerated and re-verified against the named Git commits")
        git_reverified = True
    else:
        limitations.append("Git content re-verification skipped: pass --repo-root to re-check each manifest against its commit")
    return {"base": base_doc, "head": head_doc,
            "baseExport": Path(args.base), "headExport": Path(args.head),
            "change": load_change_record(args.change) if args.change else None,
            "checks": checks, "limitations": limitations, "gitReverified": git_reverified}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--project", help="Exact LikeC4 projectId (required if export contains distinct projects)")
    p.add_argument("--base-provenance", help="Provenance JSON recorded for --base by provenance.py")
    p.add_argument("--head-provenance", help="Provenance JSON recorded for --head by provenance.py")
    p.add_argument("--base-ref", help="Exact 40-character Git commit the base provenance must name")
    p.add_argument("--head-ref", help="Exact 40-character Git commit the head provenance must name")
    p.add_argument("--change", help="Optional change record whose bytes are bound into the review fingerprint")
    p.add_argument("--repo-root", help="Re-verify each source manifest against its Git commit in this repository")
    a = p.parse_args(argv)
    try:
        report = compare(load(a.base, a.project), load(a.head, a.project), build_review(a))
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError) as ex:
        p.exit(2, f"Cannot compare model exports: {ex}\n")


if __name__ == "__main__":
    raise SystemExit(main())
