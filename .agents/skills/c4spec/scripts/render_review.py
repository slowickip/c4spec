#!/usr/bin/env python3
"""Render an existing C4Spec diff/check report and native LikeC4 PNGs offline.

This is a reviewer adapter, not a renderer: it never re-layouts the model, never
reads ``.c4`` sources and never invents a second graph. Inputs are the JSON that
``diff.py`` and ``check.py`` already produce plus PNG files exported by the
canonical LikeC4 compiler. Outputs are temporary, untracked artifacts: one
self-contained HTML file (CSP, escaped text, no scripts, no network) and an
optional GitHub Markdown summary.

It records no approval. ``check.py`` structural success is never presented as
test execution; ``reviewStatus``/``reviewAssurance`` are reported verbatim.

Each artifact is written through a unique same-directory temporary file created
exclusively and renamed into place, so a half-written file is never visible and a
pre-planted temporary name cannot be followed. The outputs are not one transaction.
If a later write fails, artifacts that this run created are removed again, while
pre-existing artifacts already replaced under ``--force`` are kept (a consistent
prefix) and reported as committed in the ``status: partial`` error output.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile

SCHEMA_VERSION = 1
STATUS = "ADVISORY REVIEW ARTIFACT — NO APPROVAL RECORDED"
FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SECTIONS = ("elements", "relationships", "views")
OPERATIONS = ("added", "removed", "modified")
DIFF_KEYS = frozenset({
    "schemaVersion", "projectId", "elements", "relationships", "views",
    "reviewHints", "fingerprint", "fingerprintScope", "limitations",
    "reviewStatus", "reviewFingerprint", "reviewFingerprintScope",
    "reviewBinding", "reviewAssurance", "reviewLimitations",
    "humanApprovalVerified",
})
CHANGE_KEYS = frozenset({
    "schemaVersion", "id", "intent", "scope", "constraints", "evidence",
    "alternatives", "decision", "rationale", "openQuestions",
})
EVIDENCE_STATES = frozenset({"planned", "declared", "inferred", "observed"})
CHECK_KEYS = frozenset({
    "schemaVersion", "phase", "valid", "errors", "warnings",
    "implementationConformanceVerified", "runtimeVerified", "testsExecuted",
    "limitations", "findings",
})
CSS = """
:root{color-scheme:light;font-family:system-ui,sans-serif;color:#15233b;background:#f4f6fa}
body{max-width:1180px;margin:0 auto;padding:32px 24px;line-height:1.55}
h1,h2,h3{line-height:1.2}h1{font-size:1.95rem}h2{margin-top:34px;border-bottom:1px solid #dbe2ed;padding-bottom:6px}
.notice{border-left:5px solid #ba6500;background:#fff4df;padding:16px 20px;border-radius:8px;margin:16px 0}
.stop{border-left:5px solid #bb3046;background:#fdecef;padding:16px 20px;border-radius:8px;margin:16px 0}
.card{background:white;border:1px solid #dbe2ed;border-radius:10px;padding:16px;margin:12px 0}
table{border-collapse:collapse;width:100%;margin:10px 0}
.table-scroll{overflow-x:auto;max-width:100%}
table.alternatives{min-width:36rem}
table.alternatives th:nth-child(3),table.alternatives td:nth-child(3){white-space:nowrap;width:6.5rem}
table.constraints,table.evidence{overflow-wrap:normal}
table.constraints th,table.evidence th{white-space:nowrap}
table.constraints td:nth-child(1),table.constraints td:nth-child(3),table.constraints td:nth-child(4),
table.constraints td:nth-child(5),table.evidence td:nth-child(1),table.evidence td:nth-child(2),
table.evidence td:nth-child(3){white-space:nowrap}
th,td{border-bottom:1px solid #dbe2ed;padding:8px 10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#edf2f8}code,pre{font-family:ui-monospace,monospace}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fb;padding:12px;border-radius:6px;font-size:.82rem}
.muted{color:#52617a}.tag{font-size:.78rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.added{color:#18794e}.removed{color:#bb3046}.modified{color:#205bb5}
.render{overflow:auto;border:1px solid #dbe2ed;border-radius:8px;background:white;padding:8px}
.render img{max-width:none;height:auto}
figure{margin:16px 0}figcaption{color:#52617a;font-size:.85rem;margin-top:6px}
"""


class InputError(ValueError):
    """Unusable or unsafe packet input."""


class PartialWrite(InputError):
    """A late write failed after some artifacts were already committed."""

    def __init__(self, message, committed, removed):
        super().__init__(message)
        self.committed = committed
        self.removed = removed


def display_text(value):
    """Lossless text for display: never emit unpaired surrogates or control chars."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, sort_keys=True)
    return "".join(c if (c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF or
                         0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
                   else "\ufffd" for c in text)


def esc(value):
    return html.escape(display_text(value), quote=True)


MD_META = re.compile(r"([\\`*_{}\[\]#+!|>~])")


def md_cell(value):
    """One-line Markdown table cell with every Markdown metacharacter escaped."""
    text = " ".join(display_text(value).split())
    return MD_META.sub(r"\\\1", text)


def md_code(value):
    """Markdown code span that survives backticks, pipes and leading/trailing ticks."""
    text = " ".join(display_text(value).split()).replace("|", "\\|")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    if text.startswith("`") or text.endswith("`") or text == "":
        return f"{fence} {text} {fence}"
    return fence + text + fence


def fenced(value):
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}json\n{text}\n{fence}"


def read_json(path, label):
    def reject(value):
        raise ValueError("non-JSON numeric constant " + str(value))

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)
    except (OSError, UnicodeError, ValueError) as exc:
        raise InputError(f"cannot read {label} JSON: {path}: {exc}") from exc


def validate_diff(document):
    if not isinstance(document, dict):
        raise InputError("diff report must be a JSON object")
    if type(document.get("schemaVersion")) is not int or document["schemaVersion"] != SCHEMA_VERSION:
        raise InputError("diff report must declare schemaVersion=1")
    unknown = set(document) - DIFF_KEYS
    if unknown:
        raise InputError("diff report has fields this adapter does not understand: " + ", ".join(sorted(unknown)))
    if not isinstance(document.get("projectId"), str) or not document["projectId"]:
        raise InputError("diff report needs a non-empty projectId")
    if not FINGERPRINT.match(str(document.get("fingerprint", ""))):
        raise InputError("diff report fingerprint must be a sha256: value")
    for section in SECTIONS:
        block = document.get(section)
        if not isinstance(block, dict) or any(not isinstance(block.get(op), list) for op in OPERATIONS):
            raise InputError("diff report needs " + section + " with added/removed/modified lists")
    for section in ("elements", "views"):
        for key in ("fieldChanges", "addedDetails", "removedDetails"):
            if key in document[section] and not isinstance(document[section][key], dict):
                raise InputError(f"diff report {section}.{key} must be an object")
    for entry in document["relationships"]["added"] + document["relationships"]["removed"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("relationship"), dict):
            raise InputError("relationship added/removed entries must wrap a relationship object")
    for entry in document["relationships"]["modified"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("identity"), dict):
            raise InputError("relationship modified entries must carry an identity object")
    status = document.get("reviewStatus")
    if status is not None and status not in {"exploratory", "source-bound-self-declared", "source-bound-reverified"}:
        raise InputError("diff report reviewStatus is not a known value: " + str(status))
    bound = document.get("reviewFingerprint")
    if bound is not None and not FINGERPRINT.match(str(bound)):
        raise InputError("reviewFingerprint must be null or a sha256: value")
    for key in ("limitations", "reviewLimitations", "reviewHints"):
        value = document.get(key)
        if value is not None and (not isinstance(value, list) or any(not isinstance(x, str) for x in value)):
            raise InputError(f"diff report {key} must be a list of strings")
    json.dumps(document, allow_nan=False)
    return document


def validate_check(document):
    if not isinstance(document, dict):
        raise InputError("check report must be a JSON object")
    if type(document.get("schemaVersion")) is not int or document["schemaVersion"] != SCHEMA_VERSION:
        raise InputError("check report must declare schemaVersion=1")
    unknown = set(document) - CHECK_KEYS
    if unknown:
        raise InputError("check report has fields this adapter does not understand: " + ", ".join(sorted(unknown)))
    for key in ("valid", "testsExecuted"):
        if not isinstance(document.get(key), bool):
            raise InputError(f"check report {key} must be a boolean")
    for key in ("errors", "warnings"):
        if type(document.get(key)) is not int or document[key] < 0:
            raise InputError(f"check report {key} must be a non-negative integer")
    findings = document.get("findings")
    if not isinstance(findings, list):
        raise InputError("check report findings must be a list")
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("severity") not in {"error", "warning"}:
            raise InputError("every finding needs a severity of error or warning")
        for key in ("code", "location", "message"):
            if not isinstance(finding.get(key), str):
                raise InputError("every finding needs string " + key)
    json.dumps(document, allow_nan=False)
    return document


def validate_change(document):
    if not isinstance(document, dict):
        raise InputError("change record must be a JSON object")
    if type(document.get("schemaVersion")) is not int or document["schemaVersion"] != 1:
        raise InputError("change record must declare schemaVersion=1")
    unknown = set(document) - CHANGE_KEYS
    if unknown:
        raise InputError("change record has fields this adapter does not understand: " + ", ".join(sorted(unknown)))
    for key in ("id", "intent"):
        if not isinstance(document.get(key), str) or not document[key]:
            raise InputError("change record needs a non-empty " + key)
    if not isinstance(document.get("scope"), list) or any(not isinstance(x, str) for x in document["scope"]):
        raise InputError("change record scope must be a list of strings")
    for key in ("constraints", "evidence", "alternatives", "openQuestions"):
        if not isinstance(document.get(key, []), list):
            raise InputError(f"change record {key} must be a list")
    for item in document.get("evidence", []):
        if not isinstance(item, dict) or item.get("state") not in EVIDENCE_STATES:
            raise InputError("every evidence entry needs a known state: " + ", ".join(sorted(EVIDENCE_STATES)))
        for key in ("element", "path"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise InputError("every evidence entry needs a non-empty " + key)
    for item in document.get("constraints", []):
        if not isinstance(item, dict) or not isinstance(item.get("statement"), str):
            raise InputError("every constraint needs a statement")
    for item in document.get("alternatives", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise InputError("every alternative needs an id")
    json.dumps(document, allow_nan=False)
    return document


def bind_change(change, change_sha, diff):
    """Compare the supplied change record with the one hashed into the review fingerprint."""
    binding = (diff.get("reviewBinding") or {}).get("change")
    if not binding:
        return {"bound": False, "id": change["id"], "sha256": change_sha, "reason": "diff report carries no change binding"}
    if binding.get("id") != change["id"]:
        raise InputError("the supplied change record id does not match the review fingerprint: "
                         f"{change['id']!r} vs {binding.get('id')!r}")
    if binding.get("sha256") != change_sha:
        raise InputError("the supplied change record bytes do not match the review fingerprint: edited after "
                         f"diff creation? fingerprint has sha256:{binding.get('sha256')}, file has sha256:{change_sha}")
    return {"bound": True, "id": change["id"], "sha256": change_sha, "reason": "matches reviewBinding.change"}


def read_render(spec):
    if "=" not in str(spec):
        raise InputError("--render must be VIEW_ID=PATH, got: " + str(spec))
    view, raw = str(spec).split("=", 1)
    view = view.strip()
    if not view:
        raise InputError("--render needs a non-empty view id")
    path = Path(raw)
    if path.is_symlink():
        raise InputError("render must not be a symlink: " + str(path))
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read render for {view}: {path}: {exc}") from exc
    if not data.startswith(PNG_MAGIC):
        raise InputError(f"render for {view} is not a PNG file: {path}")
    return {"view": view, "path": path, "data": data}


def changed_views(diff):
    return {op: list(diff["views"][op]) for op in OPERATIONS}


def render_warnings(diff, renders):
    warnings = []
    supplied = {item["view"] for item in renders}
    changed = changed_views(diff)
    for view in changed["added"] + changed["modified"]:
        if view not in supplied:
            warnings.append("no native LikeC4 PNG supplied for changed view '" + view + "'")
    for view in changed["removed"]:
        warnings.append("view '" + view + "' was removed; the head export cannot render it")
    known = set(diff["views"].get("fieldChanges", {})) | set(changed["added"]) | set(changed["modified"]) | set(changed["removed"])
    for view in sorted(supplied - known):
        warnings.append("render '" + view + "' is not correlated with any changed view in this diff")
    return warnings


def topology_changed(diff):
    return any(diff[section][op] for section in ("elements", "relationships") for op in OPERATIONS)


def field_rows(changes):
    rows = []
    for key in sorted(changes):
        entry = changes[key] if isinstance(changes[key], dict) else {"after": changes[key]}
        before = entry.get("before") if entry.get("beforePresent", True) else None
        after = entry.get("after") if entry.get("afterPresent", True) else None
        rows.append((key, "<absent>" if entry.get("beforePresent") is False else json_text(before),
                     "<absent>" if entry.get("afterPresent") is False else json_text(after)))
    return rows


def json_text(value):
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value


def element_rows(diff):
    rows = []
    for op in OPERATIONS:
        block = diff["elements"]
        details = block.get("addedDetails" if op == "added" else "removedDetails", {}) if op != "modified" else {}
        for element in block[op]:
            summary = details.get(element, {})
            label = summary.get("title") or element
            rows.append((op, element, label, summary.get("kind", ""),
                         summary.get("technology", ""), block.get("fieldChanges", {}).get(element, {})))
    return rows


def relation_rows(diff):
    rows = []
    for op in ("added", "removed"):
        for entry in diff["relationships"][op]:
            rel = entry["relationship"]
            rows.append((op, rel.get("source", ""), rel.get("target", ""), rel.get("kind", ""),
                         rel.get("title", ""), entry.get("count", 1), {}))
    for entry in diff["relationships"]["modified"]:
        identity = entry["identity"]
        rows.append(("modified", identity.get("source", ""), identity.get("target", ""),
                     identity.get("kind", ""), identity.get("title", ""), 1, entry.get("fieldChanges", {})))
    return rows


def view_rows(diff):
    rows = []
    for op in OPERATIONS:
        for view in diff["views"][op]:
            rows.append((op, view, diff["views"].get("fieldChanges", {}).get(view, {})))
    return rows


def fingerprint_rows(diff):
    rows = [("model-only fingerprint", diff.get("fingerprint", "")),
            ("model-only scope", diff.get("fingerprintScope", ""))]
    status = diff.get("reviewStatus")
    if status is None:
        rows.append(("reviewStatus", "not reported by this diff (legacy model-only report)"))
    else:
        rows.append(("reviewStatus", status))
        rows.append(("reviewFingerprint", diff.get("reviewFingerprint") or "none — unbound comparison"))
        assurance = diff.get("reviewAssurance") or {}
        if assurance:
            for key in sorted(assurance):
                rows.append(("reviewAssurance." + key, json_text(assurance[key])))
        binding = diff.get("reviewBinding") or {}
        for side in ("base", "head"):
            entry = binding.get(side) or {}
            if not entry:
                continue
            rows.append((side + " commit", entry.get("gitCommit", "")))
            rows.append((side + " compiler", entry.get("compilerVersion", "")))
            rows.append((side + " compiler command reported",
                         json_text(entry.get("compilerCommandReported"))))
            rows.append((side + " sources digest", entry.get("sourcesDigest", "")))
        change = binding.get("change")
        if change:
            rows.append(("change record", str(change.get("id", "")) + " sha256:" + str(change.get("sha256", ""))))
    return rows


def summary_line(diff, renders, change=None):
    """Human sentence that never hides a view-only change or a missing image."""
    supplied = {item["view"] for item in renders}
    element_count = sum(len(diff["elements"][op]) for op in OPERATIONS)
    relation_count = sum(len(diff["relationships"][op]) for op in OPERATIONS)
    views = changed_views(diff)
    view_count = sum(len(views[op]) for op in OPERATIONS)
    renderable = views["added"] + views["modified"]
    missing = [view for view in renderable if view not in supplied]
    if element_count == 0 and relation_count == 0 and view_count:
        names = ", ".join(display_text(view) for view in views["added"] + views["modified"] + views["removed"])
        lead = ("No element or relationship changes. The reviewed delta is " + str(view_count)
                + " view(s): " + names + ".")
        if not renderable:
            return lead + " Removed views cannot be rendered from the head export."
        if missing:
            return (lead + " No native LikeC4 PNG was supplied for: " + ", ".join(display_text(view) for view in missing)
                    + " — this packet has no visual evidence for those views.")
        return lead + " Caller-supplied PNGs for the changed views are embedded below; their origin is not verified."
    if element_count == 0 and relation_count == 0 and not view_count:
        if change is not None:
            tail = ("A caller-supplied PNG is embedded below for context." if renders
                    else "No PNG was supplied, which is expected when the model itself does not change.")
            return ("No C4 model delta. The reviewed change is behavioral or configuration only; its intent, "
                    "alternatives, constraints and declared evidence are in the proposal record. " + tail)
        if renders:
            return ("The comparator reports no semantic delta; the supplied PNGs are context only and "
                    "their origin is not verified.")
        return ("The comparator reports no semantic delta and no PNG was supplied; this packet contains no "
                "visual evidence.")
    return (str(element_count) + " element change(s), " + str(relation_count) + " relationship change(s), "
            + str(view_count) + " view change(s).")

def html_inventory(diff):
    parts = []
    elements = element_rows(diff)
    parts.append("<h2>Element changes</h2>")
    if not elements:
        parts.append('<p class="muted">No element changes reported.</p>')
    else:
        parts.append("<table><thead><tr><th>Change</th><th>Element</th><th>Name</th><th>Kind</th>"
                     "<th>Technology</th><th>Field changes</th></tr></thead><tbody>")
        for op, eid, label, kind, tech, changes in elements:
            cells = "".join(
                f"<tr><td><span class='tag {op}'>{esc(op)}</span></td><td><code>{esc(eid)}</code></td>"
                f"<td>{esc(label)}</td><td>{esc(kind)}</td><td>{esc(tech)}</td><td>{fields_html(changes)}</td></tr>")
            parts.append(cells)
        parts.append("</tbody></table>")
    parts.append("<h2>Relationship changes</h2>")
    relations = relation_rows(diff)
    if not relations:
        parts.append('<p class="muted">No relationship changes reported.</p>')
    else:
        parts.append("<table><thead><tr><th>Change</th><th>From</th><th>To</th><th>Kind</th>"
                     "<th>Label</th><th>Count</th><th>Field changes</th></tr></thead><tbody>")
        for op, source, target, kind, title, count, changes in relations:
            parts.append(f"<tr><td><span class='tag {op}'>{esc(op)}</span></td><td><code>{esc(source)}</code></td>"
                         f"<td><code>{esc(target)}</code></td><td>{esc(kind)}</td><td>{esc(title)}</td>"
                         f"<td>{esc(count)}</td><td>{fields_html(changes)}</td></tr>")
        parts.append("</tbody></table>")
    parts.append("<h2>View changes</h2>")
    views = view_rows(diff)
    if not views:
        parts.append('<p class="muted">No view changes reported.</p>')
    else:
        parts.append("<table><thead><tr><th>Change</th><th>View</th><th>Field changes</th></tr></thead><tbody>")
        for op, view, changes in views:
            parts.append(f"<tr><td><span class='tag {op}'>{esc(op)}</span></td><td><code>{esc(view)}</code></td>"
                         f"<td>{fields_html(changes)}</td></tr>")
        parts.append("</tbody></table>")
    return "".join(parts)


def fields_html(changes):
    rows = field_rows(changes or {})
    if not rows:
        return '<span class="muted">none</span>'
    return "<br>".join(f"<code>{esc(key)}</code>: {esc(before)} → {esc(after)}" for key, before, after in rows)


def change_html(change, binding=None):
    if change is None:
        return ""
    scope = ", ".join(display_text(item) for item in change["scope"]) or "none declared"
    parts = ['<h2>Proposal record — author-declared, not approved</h2>',
             '<div class="notice">These are the author\'s claims from the change record. This packet does not '
             'approve them, does not execute their evidence and does not verify an observed claim.</div>']
    if binding and binding.get("bound"):
        parts.append(f'<p class="muted">Change record bytes bound to the review fingerprint: '
                     f'<code>sha256:{esc(binding["sha256"])}</code></p>')
    else:
        parts.append('<div class="stop"><strong>This change record is not bound to the review fingerprint.</strong> '
                     'The diff report carries no change binding, so the proposal below could differ from the one '
                     'that was reviewed. Re-run diff.py with --change to bind it.</div>')
    parts += [
             f"<p><strong>{esc(change['id'])}</strong> — {esc(change['intent'])}</p>",
             f"<p class=\"muted\">scope: {esc(scope)} · decision: {esc(change.get('decision') or 'none recorded')}</p>"]
    if change.get("rationale"):
        parts.append(f"<p>{esc(change['rationale'])}</p>")
    alternatives = change.get("alternatives") or []
    if alternatives:
        parts.append("<h3>Alternatives</h3><table class=\"alternatives\"><thead><tr><th>Alternative</th><th>Trade-off</th><th>Chosen</th>"
                     "</tr></thead><tbody>")
        chosen = change.get("decision")
        for item in alternatives:
            parts.append(f"<tr><td><code>{esc(item['id'])}</code>{(' — ' + esc(item['title'])) if item.get('title') else ''}</td>"
                         f"<td>{esc(item.get('tradeoff', ''))}</td>"
                         f"<td>{'yes' if item['id'] == chosen else ''}</td></tr>")
        parts.append("</tbody></table>")
    constraints = change.get("constraints") or []
    if constraints:
        parts.append("<h3>Constraints</h3><table class=\"constraints\"><thead><tr><th>Id</th><th>Statement</th><th>Durability</th>"
                     "<th>Applies to</th><th>Verification refs</th></tr></thead><tbody>")
        for item in constraints:
            parts.append(f"<tr><td><code>{esc(item.get('id', ''))}</code></td><td>{esc(item.get('statement', ''))}</td>"
                         f"<td>{esc(item.get('durability', ''))}</td>"
                         f"<td>{esc(', '.join(item.get('appliesTo') or []))}</td>"
                         f"<td>{esc(', '.join(item.get('verificationRefs') or []))}</td></tr>")
        parts.append("</tbody></table>")
    evidence = change.get("evidence") or []
    if evidence:
        parts.append("<h3>Evidence as declared by the author</h3><table class=\"evidence\"><thead><tr><th>State</th><th>Element</th>"
                     "<th>Path</th><th>Note</th></tr></thead><tbody>")
        for item in evidence:
            parts.append(f"<tr><td><span class='tag'>{esc(item['state'])}</span></td><td><code>{esc(item['element'])}</code></td>"
                         f"<td><code>{esc(item['path'])}</code></td><td>{esc(item.get('note', ''))}</td></tr>")
        parts.append("</tbody></table>")
        parts.append('<div class="stop"><strong>Evidence states are author claims.</strong> '
                     '<code>declared</code>/<code>planned</code> mean a path was named, not exercised; '
                     '<code>observed</code> is still not an execution log in this packet.</div>')
    questions = change.get("openQuestions") or []
    if questions:
        parts.append("<h3>Open questions</h3><ul>" + "".join(f"<li>{esc(item)}</li>" for item in questions) + "</ul>")
    return "".join(parts)


def change_markdown(change, binding=None):
    if change is None:
        return []
    lines = ["", "### Proposal record — author-declared, not approved", "",
             "> Author claims only. No approval, no executed evidence, no verified observation.", ""]
    if binding and binding.get("bound"):
        lines += [f"> Change record bytes bound to the review fingerprint: `sha256:{binding['sha256']}`.", ""]
    else:
        lines += ["> **This change record is not bound to the review fingerprint** (diff.py ran without --change); "
                  "the proposal below could differ from the one reviewed.", ""]
    lines += [
             f"- change `{md_cell(change['id'])}`", f"- intent {md_cell(change['intent'])}",
             f"- scope {md_cell(', '.join(change['scope']) or 'none declared')}",
             f"- decision {md_cell(change.get('decision') or 'none recorded')}"]
    if change.get("rationale"):
        lines.append(f"- rationale {md_cell(change['rationale'])}")
    alternatives = change.get("alternatives") or []
    if alternatives:
        lines += ["", "| Alternative | Trade-off | Chosen |", "| --- | --- | --- |"]
        for item in alternatives:
            label = md_cell(item["id"]) + (" — " + md_cell(item["title"]) if item.get("title") else "")
            lines.append(f"| {label} | {md_cell(item.get('tradeoff', ''))} | "
                         f"{'yes' if item['id'] == change.get('decision') else ''} |")
    constraints = change.get("constraints") or []
    if constraints:
        lines += ["", "| Constraint | Statement | Durability | Applies to | Verification refs |",
                  "| --- | --- | --- | --- | --- |"]
        for item in constraints:
            lines.append(f"| {md_code(item.get('id', ''))} | {md_cell(item.get('statement', ''))} | "
                         f"{md_cell(item.get('durability', ''))} | {md_cell(', '.join(item.get('appliesTo') or []))} | "
                         f"{md_cell(', '.join(item.get('verificationRefs') or []))} |")
    evidence = change.get("evidence") or []
    if evidence:
        lines += ["", "| Evidence state | Element | Path | Note |", "| --- | --- | --- | --- |"]
        for item in evidence:
            lines.append(f"| {md_cell(item['state'])} | {md_code(item['element'])} | {md_code(item['path'])} | "
                         f"{md_cell(item.get('note', ''))} |")
        lines += ["", "> Evidence states are author claims: `declared`/`planned` name a path, they do not prove it ran."]
    questions = change.get("openQuestions") or []
    if questions:
        lines += ["", "**Open questions**", ""] + [f"- {md_cell(item)}" for item in questions]
    return lines


def html_renders(renders):
    if not renders:
        return ('<h2>Rendered views</h2><p class="muted">No native LikeC4 PNG was supplied. '
                'Without one this packet carries no visual evidence.</p>')
    parts = ['<h2>Rendered views — caller-supplied PNG (format validated, origin not verified)</h2>',
             '<div class="stop">These images were supplied by the caller. Only the PNG signature was checked: '
             'this packet cannot prove which compiler produced them and does not bind an image to an export. '
             'Re-export with the pinned canonical LikeC4 compiler before treating an image as evidence.</div>']
    for item in sorted(renders, key=lambda entry: entry["view"]):
        encoded = base64.b64encode(item["data"]).decode("ascii")
        parts.append(f'<figure><div class="render"><img alt="LikeC4 render of view {esc(item["view"])}" '
                     f'src="data:image/png;base64,{encoded}"></div>'
                     f"<figcaption>view <code>{esc(item['view'])}</code> — caller-supplied PNG; signature validated, "
                     f"origin unverified; embedded as a data URI, scroll horizontally for full resolution. "
                     f"No network is used.</figcaption></figure>")
    return "".join(parts)

def html_check(check):
    if check is None:
        return ('<h2>Structural check</h2><p class="muted">No check.py report supplied; structural validity, '
                'findings and test-execution state are unknown in this packet.</p>')
    parts = ["<h2>Structural check (check.py)</h2>",
             '<div class="stop"><strong>Structural check only.</strong> check.py verifies structure and never executes '
             'tests; this renderer executed nothing. The <code>testsExecuted</code> value below is a field of the '
             'supplied report, not evidence that anything ran.</div>']
    if check["testsExecuted"]:
        parts.append('<div class="stop"><strong>The supplied report claims <code>testsExecuted=true</code>.</strong> '
                     'check.py does not run tests, so that value is caller-supplied and cannot be treated as '
                     'execution evidence here.</div>')
    parts.append(f"<p>phase <code>{esc(check.get('phase', ''))}</code> · valid <strong>{esc(check['valid'])}</strong> · "
                 f"errors <strong>{esc(check['errors'])}</strong> · warnings <strong>{esc(check['warnings'])}</strong> · "
                 f"testsExecuted <code>{esc(check['testsExecuted'])}</code> (self-reported)</p>")
    if check["findings"]:
        parts.append("<table><thead><tr><th>Severity</th><th>Code</th><th>Location</th><th>Message</th>"
                     "</tr></thead><tbody>")
        for finding in check["findings"]:
            parts.append(f"<tr><td>{esc(finding['severity'])}</td><td><code>{esc(finding['code'])}</code></td>"
                         f"<td><code>{esc(finding['location'])}</code></td><td>{esc(finding['message'])}</td></tr>")
        parts.append("</tbody></table>")
    else:
        parts.append('<p class="muted">No findings reported.</p>')
    return "".join(parts)

def fingerprint_html(diff):
    rows = fingerprint_rows(diff)
    return ("<table><tbody>" + "".join(
        f"<tr><th>{esc(label)}</th><td><code>{esc(value)}</code></td></tr>" for label, value in rows) + "</tbody></table>")


def limitations_html(diff, warnings):
    items = list(warnings) + list(diff.get("reviewLimitations") or []) + list(diff.get("limitations") or [])
    seen, unique = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return ("<ul>" + "".join(f"<li>{esc(item)}</li>" for item in unique) + "</ul>") if unique \
        else '<p class="muted">No limitations were supplied by the diff report.</p>'


def wrap_tables(text):
    """Give every table its own horizontal scroller so a narrow viewport scrolls instead of crushing."""
    return re.sub(r"<table([^>]*)>(.*?)</table>",
                  r'<div class="table-scroll"><table\1>\2</table></div>', text, flags=re.S)


def document_html(diff, check, renders, warnings, change=None, binding=None):
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc('C4Spec review packet — ' + diff['projectId'])}</title>
<style>{CSS}</style></head><body>
<p class="tag muted">C4Spec offline review packet</p>
<h1>Architecture review — <code>{esc(diff['projectId'])}</code></h1>
<div class="notice"><strong>{esc(STATUS)}.</strong> This file is generated review material. It is not a signature,
not a human approval and not a merge decision; those remain explicit GitHub actions by the owner.</div>
<p>{esc(summary_line(diff, renders, change))}</p>
<h2>Review identity</h2>
{fingerprint_html(diff)}
{change_html(change, binding)}
<h2>Complete semantic inventory</h2>
{html_inventory(diff)}
{html_renders(renders)}
{html_check(check)}
<h2>Limitations and remaining review</h2>
{limitations_html(diff, warnings)}
<div class="stop">The comparator covers a conservative subset of computed LikeC4 semantics. View selector rules,
deployment blocks, layout, unexported source and runtime state require separate source and runtime review.</div>
</body></html>
"""
    return wrap_tables(page)


def markdown(diff, check, renders, warnings, asset_names, change=None, binding=None):
    lines = [f"## C4Spec review packet — {md_code(diff['projectId'])}", "",
             f"> **{STATUS}.** Generated review material, not a signature, not human approval, not a merge decision.", "",
             md_cell(summary_line(diff, renders, change)), "", "### Review identity", "",
             "| Item | Value |", "| --- | --- |"]
    for label, value in fingerprint_rows(diff):
        lines.append(f"| {md_cell(label)} | {md_code(value)} |")
    lines += change_markdown(change, binding)
    lines += ["", "### Element changes", ""]
    elements = element_rows(diff)
    if not elements:
        lines.append("_No element changes reported._")
    else:
        lines += ["| Change | Element | Name | Kind | Technology | Field changes |", "| --- | --- | --- | --- | --- | --- |"]
        for op, eid, label, kind, tech, changes in elements:
            lines.append(f"| {op} | {md_code(eid)} | {md_cell(label)} | {md_cell(kind)} | {md_cell(tech)} | "
                         f"{md_cell(fields_md(changes))} |")
    lines += ["", "### Relationship changes", ""]
    relations = relation_rows(diff)
    if not relations:
        lines.append("_No relationship changes reported._")
    else:
        lines += ["| Change | From | To | Kind | Label | Count | Field changes |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for op, source, target, kind, title, count, changes in relations:
            lines.append(f"| {op} | {md_code(source)} | {md_code(target)} | {md_cell(kind)} | "
                         f"{md_cell(title)} | {md_cell(count)} | {md_cell(fields_md(changes))} |")
    lines += ["", "### View changes", ""]
    views = view_rows(diff)
    if not views:
        lines.append("_No view changes reported._")
    else:
        lines += ["| Change | View | Field changes |", "| --- | --- | --- |"]
        for op, view, changes in views:
            lines.append(f"| {op} | {md_code(view)} | {md_cell(fields_md(changes))} |")
    if renders:
        lines += ["", "### Rendered views (caller-supplied PNG, origin not verified)", "",
                  "> Only the PNG signature was validated. This packet cannot prove which compiler produced these "
                  "images; re-export with the pinned canonical LikeC4 compiler before treating them as evidence.", ""]
        for item in sorted(renders, key=lambda entry: entry["view"]):
            name = asset_names[item["view"]]
            lines.append(f"![LikeC4 render of view {md_cell(item['view'])}]({name})")
            lines.append("")
    if check is not None:
        lines += ["", "### Structural check (check.py)", "",
                  "> **Structural check only.** check.py verifies structure and never executes tests; this renderer "
                  "executed nothing. `testsExecuted` is a field of the supplied report, not execution evidence.", ""]
        if check["testsExecuted"]:
            lines += ["> **The supplied report claims `testsExecuted=true`.** check.py does not run tests, so that "
                      "value is caller-supplied and cannot be treated as execution evidence here.", ""]
        lines += [f"- phase {md_code(check.get('phase', ''))}", f"- valid **{check['valid']}**",
                  f"- errors **{check['errors']}**, warnings **{check['warnings']}**",
                  f"- testsExecuted {md_code(check['testsExecuted'])} (self-reported)"]
        if check["findings"]:
            lines += ["", "| Severity | Code | Location | Message |", "| --- | --- | --- | --- |"]
            for finding in check["findings"]:
                lines.append(f"| {finding['severity']} | {md_code(finding['code'])} | "
                             f"{md_code(finding['location'])} | {md_cell(finding['message'])} |")
    lines += ["", "### Limitations and remaining review", ""]
    items = list(dict.fromkeys(list(warnings) + list(diff.get("reviewLimitations") or [])
                               + list(diff.get("limitations") or [])))
    if items:
        lines += [f"- {md_cell(item)}" for item in items]
    else:
        lines.append("_No limitations were supplied by the diff report._")
    lines += ["", "The comparator covers a conservative subset of computed LikeC4 semantics. View selector rules, "
                  "deployment blocks, layout, unexported source and runtime state require separate source and runtime review.", ""]
    return "\n".join(lines)

def fields_md(changes):
    rows = field_rows(changes or {})
    if not rows:
        return "none"
    return "; ".join(f"{key}: {before} -> {after}" for key, before, after in rows)


def plan_assets(md_path, renders, inputs, force):
    """Validate every derived asset path before anything is written."""
    assets = md_path.parent / (md_path.stem + "-assets")
    if assets.is_symlink():
        raise InputError("Markdown asset directory must not be a symlink: " + str(assets))
    input_set = {path.resolve() for path in inputs}
    plan, asset_names, seen = [], {}, {}
    for item in sorted(renders, key=lambda entry: entry["view"]):
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", item["view"]).strip("-")
        if name in {"", ".", ".."}:
            raise InputError("view id cannot be turned into a safe asset name: " + str(item["view"]))
        target = assets / (name + ".png")
        if target.is_symlink():
            raise InputError("render asset must not be a symlink: " + str(target))
        if target.resolve() in input_set:
            raise InputError("render asset would overwrite an input file: " + str(target))
        if "architecture" in target.resolve().parts:
            raise InputError("refusing to write an artifact under an architecture/ directory: " + str(target))
        if name in seen and seen[name] != item["data"]:
            raise InputError("two renders map to the same asset name with different bytes: " + name)
        if target.exists() and target.read_bytes() != item["data"] and not force:
            raise InputError("render asset exists with different bytes; pass --force: " + str(target))
        if name not in seen:
            plan.append((target, item["data"]))
        seen[name] = item["data"]
        asset_names[item["view"]] = assets.name + "/" + target.name
    return assets, plan, asset_names


def write_atomic(path, data):
    """Write through an exclusive, unpredictable same-directory temporary file."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    handle_fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp",
                                            dir=str(path.parent))
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def check_assurance_warnings(check):
    if check is not None and check["testsExecuted"]:
        return ["the supplied check report claims testsExecuted=true; check.py never executes tests, so the value "
                "is caller-supplied and not execution evidence"]
    return []

def check_outputs(outputs, inputs, force):
    paths = [path for path in outputs if path]
    for path in paths:
        if path.is_symlink():
            raise InputError("output must not be a symlink: " + str(path))
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise InputError("output paths must be distinct")
    input_paths = {path.resolve() for path in inputs if path}
    for path, raw in zip(resolved, paths):
        if path in input_paths:
            raise InputError("output would overwrite an input file: " + str(raw))
        if raw.suffix.lower() not in {".html", ".htm", ".md"}:
            raise InputError("output must be .html or .md: " + str(raw))
        if "architecture" in path.parts:
            raise InputError("refusing to write an artifact under an architecture/ directory: " + str(raw))
        if path.exists() and not force:
            raise InputError("output already exists; pass --force to replace your own artifact: " + str(raw))
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", required=True, help="JSON written by diff.py")
    parser.add_argument("--check", help="Optional check.py JSON for the same revision")
    parser.add_argument("--change", help="Optional change record the diff was reviewed against")
    parser.add_argument("--render", action="append", default=[], metavar="VIEW_ID=PATH",
                        help="Native LikeC4 PNG for a view; repeatable")
    parser.add_argument("--html", help="Offline HTML packet path")
    parser.add_argument("--markdown", help="GitHub Markdown summary path")
    parser.add_argument("--force", action="store_true", help="Replace existing artifact files")
    args = parser.parse_args(argv)
    if not args.html and not args.markdown:
        parser.error("provide --html, --markdown, or both")
    try:
        diff = validate_diff(read_json(args.diff, "diff"))
        check = validate_check(read_json(args.check, "check")) if args.check else None
        change, binding = None, None
        if args.change:
            change_bytes = Path(args.change).read_bytes()
            change = validate_change(json.loads(change_bytes.decode("utf-8")))
            binding = bind_change(change, hashlib.sha256(change_bytes).hexdigest(), diff)
        renders = [read_render(spec) for spec in args.render]
        views = [item["view"] for item in renders]
        duplicate = {view for view in views if views.count(view) > 1}
        if duplicate:
            raise InputError("duplicate render for view(s): " + ", ".join(sorted(duplicate)))
        warnings = render_warnings(diff, renders) + check_assurance_warnings(check)
        if binding is not None and not binding["bound"]:
            warnings.append("the displayed change record is not bound to the review fingerprint: "
                            "diff.py was run without --change")
        outputs = [Path(args.html)] if args.html else []
        if args.markdown:
            outputs.append(Path(args.markdown))
        inputs = ([Path(args.diff)] + ([Path(args.check)] if args.check else [])
                  + ([Path(args.change)] if args.change else []) + [item["path"] for item in renders])
        check_outputs(outputs, inputs, args.force)
        assets_dir, asset_plan, asset_names = (plan_assets(Path(args.markdown), renders, inputs, args.force)
                                               if args.markdown else (None, [], {}))
        html_text = document_html(diff, check, renders, warnings, change, binding) if args.html else None
        md_text = markdown(diff, check, renders, warnings, asset_names, change, binding) if args.markdown else None
        written = []
        try:
            if assets_dir is not None:
                assets_dir.mkdir(parents=True, exist_ok=True)
            if md_text is not None:
                Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
            if html_text is not None:
                Path(args.html).parent.mkdir(parents=True, exist_ok=True)
            for target, data in asset_plan:
                if target.exists() and target.read_bytes() == data:
                    continue
                existed = target.exists()
                write_atomic(target, data)
                written.append((target, existed))
            final_outputs = []
            if md_text is not None:
                final_outputs.append((Path(args.markdown), md_text))
            if html_text is not None:
                final_outputs.append((Path(args.html), html_text))
            for path, text in final_outputs:
                existed = path.exists()
                write_atomic(path, text)
                written.append((path, existed))
        except OSError as exc:
            committed, removed = [], []
            for path, existed in reversed(written):
                if existed:
                    committed.append(str(path))
                    continue
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError:
                    pass
            raise PartialWrite(
                f"{exc}; already replaced (kept): {', '.join(committed) or 'none'}; "
                f"removed new artifacts: {', '.join(removed) or 'none'}", committed, removed) from exc
        print(json.dumps({"schemaVersion": SCHEMA_VERSION, "status": "advisory",
                          "outputs": [str(path) for path in outputs],
                          "renders": sorted(views),
                          "change": change["id"] if change is not None else None,
                          "changeBinding": binding,
                          "renderAssurance": {"formatValidated": bool(renders), "originVerified": False,
                                              "exportBound": False},
                          "checkAssurance": ({"testsExecutedSelfReported": check["testsExecuted"],
                                              "testsExecutedVerified": False} if check is not None else None),
                          "warnings": warnings,
                          "diffFingerprint": diff["fingerprint"],
                          "reviewFingerprint": diff.get("reviewFingerprint"),
                          "humanApprovalVerified": False}, sort_keys=True))
        return 0
    except PartialWrite as exc:
        print(json.dumps({"schemaVersion": SCHEMA_VERSION, "status": "partial", "error": str(exc),
                          "committedOutputs": exc.committed, "removedOutputs": exc.removed},
                         sort_keys=True), file=sys.stderr)
        return 2
    except (InputError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"schemaVersion": SCHEMA_VERSION, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
