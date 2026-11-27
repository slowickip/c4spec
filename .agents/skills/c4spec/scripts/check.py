#!/usr/bin/env python3
"""Advisory C4Spec validation: change/constraint schemas, refs and C4 model quality."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ModuleNotFoundError as ex:
    raise SystemExit(
        f"Missing jsonschema for {sys.executable}. Install the bundled dependency with: "
        f"{sys.executable} -m pip install -r {Path(__file__).resolve().parent.parent / 'requirements.txt'}"
    ) from ex
from diff import select_project  # Share released LikeC4 export selection with diff.py

ROOT = Path(__file__).resolve().parent.parent
DETAIL_NAME = re.compile(r"(?:\.ya?ml$|\.json$|(?:Controller|Repository|DTO)$|^(?:helmrelease|externalsecret)[-_.])", re.I)


class InputError(ValueError):
    pass


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as ex:
        raise InputError(f"Cannot read JSON: {path}") from ex


def validate_schema(data, schema):
    spec = read_json(ROOT / "schemas" / schema)
    validator = Draft202012Validator(spec, format_checker=FormatChecker())
    return list(validator.iter_errors(data))


def path_exists(root, raw):
    if not isinstance(raw, str) or not raw or any(c in raw for c in "\\:*?[]#\x00\n\r") or raw.startswith("~"):
        raise InputError("Evidence reference must be a literal repository-relative path")
    p = PurePosixPath(raw)
    if p.is_absolute() or p.as_posix() in {".", ""} or ".." in p.parts:
        raise InputError("Evidence reference escapes project root")
    candidate = (root / Path(*p.parts)).resolve()
    if not candidate.is_relative_to(root):
        raise InputError("Evidence reference resolves outside project root")
    return candidate.exists() and candidate.is_file()


def records(model, project_id=None):
    try:
        return select_project(model, project_id)
    except ValueError as ex:
        raise InputError(str(ex)) from ex


def check(change=None, model=None, constraints=None, root=None, phase="proposal", view_warning=12, project_id=None):
    findings = []

    def emit(severity, code, at, message):
        findings.append({"severity": severity, "code": code, "location": at, "message": message})

    for doc, schema, label in [(change, "change.schema.json", "change"), (constraints, "constraints.schema.json", "constraints")]:
        if doc is None:
            continue
        for error in validate_schema(doc, schema):
            at = ".".join([label, *(str(x) for x in error.path)])
            emit("error", "schema", at, f"JSON Schema rule {error.validator} failed")

    if any(x["code"] == "schema" for x in findings):
        return output(findings, phase)

    if change is None and model is None:
        raise InputError("Supply --model-json for model-only checks, or --change for a change record")
    change = change if change is not None else {}
    model = records(model, project_id) if model is not None else None
    if phase == "completion" and model is None:
        emit("error", "model_required", "model", "Completion checks require a computed LikeC4 model export")
    els = model["elements"] if model is not None else {}
    repo = Path(root or ".").resolve()
    if not repo.is_dir():
        raise InputError("repo-root must exist and be a directory")

    def unique(seq, where):
        vals = [x["id"] for x in seq]
        if len(vals) != len(set(vals)):
            emit("error", "duplicate_id", where, "IDs in this collection must be unique")

    unique(change.get("constraints", []), "change.constraints")
    unique(change.get("alternatives", []), "change.alternatives")
    if change.get("decision") is not None and change["decision"] not in {x["id"] for x in change.get("alternatives", [])}:
        emit("error", "unknown_decision", "change.decision", "Decision must select an existing alternative")

    for idx, eid in enumerate(change.get("scope", [])):
        if model is not None and eid not in els:
            emit("warning" if phase == "proposal" else "error", "unmapped_scope", f"change.scope.{idx}",
                 "Proposed element not yet modeled" if phase == "proposal" else "Completion scope must reference a model element")

    planned = set()
    for idx, evidence in enumerate(change.get("evidence", [])):
        path = evidence["path"]
        if evidence["state"] == "planned":
            planned.add(path)
            if phase == "completion":
                emit("error", "still_planned", f"change.evidence.{idx}", "Convert planned reference to truthful evidence state before completion")
        if model is not None and evidence["element"] not in els:
            emit("warning" if phase == "proposal" else "error", "unmapped_evidence", f"change.evidence.{idx}",
                 "Proposed element not yet modeled" if phase == "proposal" else "Completion evidence must reference a model element")
        try:
            exists = path_exists(repo, path)
            if not exists:
                if evidence["state"] == "planned" and phase == "proposal":
                    emit("warning", "planned_path", f"change.evidence.{idx}", "Planned evidence path does not yet exist")
                else:
                    emit("error", "missing_path", f"change.evidence.{idx}", "Evidence path does not exist")
        except InputError as ex:
            emit("error", "unsafe_path", f"change.evidence.{idx}", str(ex))

    def check_constraint(c, at, persistent=False):
        refs = c.get("verificationRefs", [])
        if persistent and not refs:
            emit("error", "verification_required", at, "Persistent constraints require verification references")
        if len(refs) != len(set(refs)):
            emit("error", "duplicate_ref", at, "Duplicate verification reference")
        for ref in refs:
            try:
                if not path_exists(repo, ref):
                    if phase == "proposal" and ref in planned:
                        emit("warning", "planned_path", at, "Future test/contract reference is not yet present")
                    else:
                        emit("error", "missing_path", at, "Constraint verification path does not exist")
            except InputError as ex:
                emit("error", "unsafe_path", at, str(ex))

    for i, c in enumerate(change.get("constraints", [])):
        at = f"change.constraints.{i}"
        check_constraint(c, at, c["durability"] == "persistent")
        for eid in c.get("appliesTo", []):
            if model is not None and eid not in els:
                emit("warning" if phase == "proposal" else "error", "unmapped_constraint",
                     at, "Constraint target is absent from the computed architecture")
        # Explicitly associate verificationRefs with evidence declared for this change.
        # This is only traceability: it does not execute or inspect test behavior.
        if c["durability"] == "persistent":
            for ref in c.get("verificationRefs", []):
                if not any(e["path"] == ref and (
                        not c.get("appliesTo") or e["element"] in c["appliesTo"])
                        for e in change.get("evidence", [])):
                    emit("warning" if phase == "proposal" else "error",
                         "unlinked_verification_ref", at,
                         "Persistent constraint verificationRef must have matching change evidence path and element")
    persistent_changes = [c for c in change.get("constraints", [])
                          if c["durability"] == "persistent"]
    if persistent_changes and constraints is None and phase == "completion":
        emit("warning", "register_not_checked", "constraints",
             "No durable constraint register supplied; promotion cannot be verified")
    if constraints is not None:
        unique(constraints["constraints"], "constraints.constraints")
        registered = {c["id"]: c for c in constraints["constraints"]}
        for c in persistent_changes:
            existing = registered.get(c["id"])
            if existing is None:
                emit("warning" if phase == "proposal" else "error",
                     "unpromoted_constraint", f"change.constraints.{c['id']}",
                     "Persistent change constraint is absent from the supplied durable register")
            elif (existing["statement"] != c["statement"]
                  or set(existing.get("appliesTo", [])) != set(c.get("appliesTo", []))
                  or set(existing.get("verificationRefs", [])) != set(c.get("verificationRefs", []))):
                emit("warning" if phase == "proposal" else "error",
                     "constraint_register_mismatch", f"change.constraints.{c['id']}",
                     "Persistent change constraint differs from the supplied register")
        ids = set(registered)
        for i, c in enumerate(constraints["constraints"]):
            check_constraint(c, f"constraints.constraints.{i}", True)
            if c["id"] in set(c.get("supersedes", [])):
                emit("error", "self_supersession", f"constraints.constraints.{i}", "Constraint cannot supersede itself")
            for old in c.get("supersedes", []):
                if old not in ids:
                    emit("warning", "unknown_supersession", f"constraints.constraints.{i}", "Superseded ID not in the active constraint register")
            for eid in c["appliesTo"]:
                if model is not None and eid not in els:
                    emit("error", "unmapped_constraint", f"constraints.constraints.{i}", "Durable constraint references unknown model element")

    if model is not None:
        for eid, element in els.items():
            title = element.get("title", "")
            desc = element.get("description", {})
            desc_text = desc.get("txt", desc.get("md", "")) if isinstance(desc, dict) else str(desc)
            if not title or not title.strip():
                emit("warning", "missing_name", f"model.elements.{eid}", "Element needs a meaningful name")
            if not desc_text or not desc_text.strip():
                emit("warning", "missing_responsibility", f"model.elements.{eid}", "Element needs a concise responsibility")
            if element.get("kind") in ("container", "component") and not element.get("technology"):
                emit("warning", "missing_technology", f"model.elements.{eid}", "C4 container/component should identify technology when relevant")
            if DETAIL_NAME.search(str(title)):
                emit("warning", "implementation_detail", f"model.elements.{eid}", "Potential file/class/resource-level detail; justify architectural significance")
        for rid, rel in model["relations"].items():
            if not (rel.get("title") or rel.get("description")):
                emit("warning", "unlabeled_relationship", f"model.relations.{rid}", "C4 relationship needs a meaningful purpose label")
            for endpoint in ("source", "target"):
                dest = rel.get(endpoint)
                ref = dest.get("model") if isinstance(dest, dict) else dest
                if ref and ref not in els:
                    emit("error", "dangling_relation", f"model.relations.{rid}", "Relationship endpoint not present in model export")
        for vid, view in model["views"].items():
            nodes = view.get("nodes", [])
            if isinstance(nodes, (dict, list)) and len(nodes) > view_warning:
                emit("warning", "large_view", f"model.views.{vid}", "View may be too crowded; prefer a focused view")

    return output(findings, phase)


def output(findings, phase):
    return {"schemaVersion": 1, "phase": phase, "valid": not any(x["severity"] == "error" for x in findings),
            "errors": sum(x["severity"] == "error" for x in findings),
            "warnings": sum(x["severity"] == "warning" for x in findings),
            "implementationConformanceVerified": False, "runtimeVerified": False,
            "testsExecuted": False,
            "limitations": ["Structural validation only: source file existence is not executed/passing tests or conformance proof",
                            "C4 structural validation cannot establish behavioral correctness",
                            "Computed export omits some original view selectors"],
            "findings": findings}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--change", help="Optional change record; omit for model/constraint checks")
    p.add_argument("--model-json")
    p.add_argument("--project", help="Exact LikeC4 projectId when export contains more than one project")
    p.add_argument("--constraints-file")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--phase", choices=["proposal", "completion"], default="proposal")
    p.add_argument("--view-warning", type=int, default=12)
    a = p.parse_args(argv)
    try:
        result = check(read_json(a.change) if a.change else None, read_json(a.model_json) if a.model_json else None,
                       read_json(a.constraints_file) if a.constraints_file else None,
                       a.repo_root, a.phase, a.view_warning, a.project)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1
    except InputError as ex:
        print(json.dumps({"valid": False, "error": str(ex)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
