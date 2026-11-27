#!/usr/bin/env python3
"""Adversarial probes for the consumer chain, on disposable Git revisions.

Each probe starts from one base commit, applies one source edit, commits, and
asks the real scripts what changed. The probes exist to separate detected facts
from semantics the comparator deliberately does not model:

  E  comment-only source edit          -> 0 topology, different review fingerprint
  F  view selector reordering          -> no element/relation delta
  G  reversed relationship direction   -> old relation gone, new one added
  H  parallel relationship              -> one added relation; compare generated ids
  I  planned vs declared missing path   -> proposal warning, completion failure
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import rehearse as R  # noqa: E402

WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(R.tempfile.mkdtemp(prefix="m1-probes-"))
REPO = WORK / "repo"
ART = WORK / "artifacts"
ART.mkdir(parents=True, exist_ok=True)


def commit_all(message):
    R.git(REPO, "add", "-A")
    R.git(REPO, "commit", "-q", "-m", message)
    return R.git(REPO, "rev-parse", "HEAD").stdout.strip()


def compile_side(tag, sha):
    export = ART / f"{tag}.json"
    R.likec4("validate", "--json", "--no-layout", "architecture", cwd=REPO)
    R.likec4("export", "json", "--skip-layout", "architecture", "-o", str(export), cwd=REPO)
    R.run([sys.executable, str(R.SKILL / "provenance.py"), "--model-dir", "architecture",
           "--export", str(export), "--git-commit", sha, "--compiler-version", R.COMPILER_VERSION,
           "--compiler-command", f"{R.LIKE4C4} --version", "--out", str(ART / f"{tag}-prov.json")], cwd=REPO)
    return export, ART / f"{tag}-prov.json"


def compare(tag, base_sha, head_sha, base_export, base_prov, head_export, head_prov, change=None):
    args = [sys.executable, str(R.SKILL / "diff.py"), "--base", str(base_export), "--head", str(head_export),
            "--project", R.project_id(head_export), "--base-provenance", str(base_prov),
            "--head-provenance", str(head_prov), "--base-ref", base_sha, "--head-ref", head_sha,
            "--repo-root", str(REPO)]
    if change:
        args += ["--change", str(change)]
    result = R.run(args)
    document = json.loads(result.stdout)
    (ART / f"{tag}-diff.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    return document


def counts(document):
    return {section: sum(len(document[section][op]) for op in ("added", "removed", "modified"))
            for section in ("elements", "relationships", "views")}


def probe(name, edit, expectation, extra=None):
    R.git(REPO, "checkout", "-q", "base")
    R.git(REPO, "checkout", "-q", "-B", f"probe-{name}", "base")
    edit(REPO)
    head_sha = commit_all(f"probe {name}")
    head_export, head_prov = compile_side(f"probe-{name}", head_sha)
    document = compare(f"probe-{name}", BASE_SHA, head_sha, BASE_EXPORT, BASE_PROV, head_export, head_prov)
    delta = counts(document)
    result = {"probe": name, "head": head_sha, "delta": delta,
              "modelFingerprint": document["fingerprint"], "reviewFingerprint": document["reviewFingerprint"],
              "viewsAdded": document["views"]["added"], "viewsModified": document["views"]["modified"]}
    if extra:
        result.update(extra(head_export, document))
    ok = expectation(delta, document, result)
    result["pass"] = bool(ok)
    return result


work = WORK
REPO.mkdir(parents=True, exist_ok=True)
R.copy_base(REPO)
R.git(REPO, "init", "-q", "-b", "base")
R.git(REPO, "config", "user.email", "probe@example.invalid")
R.git(REPO, "config", "user.name", "C4Spec probe")
BASE_SHA = commit_all("base")
BASE_EXPORT, BASE_PROV = compile_side("base", BASE_SHA)

# diff.py refuses two identical commits, so the zero-delta baseline is an
# empty follow-up commit: same model bytes, different commit.
R.git(REPO, "commit", "-q", "--allow-empty", "-m", "no-op baseline")
NOOP_SHA = R.git(REPO, "rev-parse", "HEAD").stdout.strip()
NOOP_EXPORT, NOOP_PROV = compile_side("noop", NOOP_SHA)
self_diff = compare("self", BASE_SHA, NOOP_SHA, BASE_EXPORT, BASE_PROV, NOOP_EXPORT, NOOP_PROV)
self_review = self_diff["reviewFingerprint"]
R.git(REPO, "checkout", "-q", "base")


def append_comment(repo):
    path = repo / "architecture" / "shop.c4"
    path.write_text(path.read_text(encoding="utf-8") + "\n// Review note only: no model statement changes here.\n",
                    encoding="utf-8")


def reorder_selector(repo):
    path = repo / "architecture" / "shop.c4"
    text = path.read_text(encoding="utf-8")
    anchor = "    include customer, shop.api, shop.db, shop.broker, shop.worker\n"
    assert anchor in text, "overview selector anchor missing"
    path.write_text(text.replace(anchor, "    include shop.worker, shop.broker, shop.db, shop.api, customer\n", 1),
                    encoding="utf-8")


def reverse_direction(repo):
    path = repo / "architecture" / "shop.c4"
    text = path.read_text(encoding="utf-8")
    anchor = "  customer -> shop.api 'Browses products' 'HTTPS'\n"
    assert anchor in text, "customer relation anchor missing"
    path.write_text(text.replace(anchor, "  shop.api -> customer 'Serves product pages' 'HTTPS'\n", 1),
                    encoding="utf-8")


def add_parallel(repo):
    path = repo / "architecture" / "shop.c4"
    text = path.read_text(encoding="utf-8")
    anchor = "  shop.api -> shop.db 'Reads and writes products' 'SQL'\n"
    assert anchor in text, "db relation anchor missing"
    path.write_text(text.replace(anchor, anchor + "  shop.api -> shop.db 'Writes audit rows' 'SQL'\n", 1),
                    encoding="utf-8")


def parallel_ids(head_export, document):
    second = ART / "probe-parallel-second.json"
    R.likec4("export", "json", "--skip-layout", "architecture", "-o", str(second), cwd=REPO)

    def relation_ids(path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        project = payload[0] if isinstance(payload, list) else payload
        relations = project.get("relations") or {}
        items = relations.values() if isinstance(relations, dict) else relations
        return {item.get("id") for item in items if isinstance(item, dict)}

    first, again = relation_ids(head_export), relation_ids(second)
    return {"idsStableAcrossCompiles": first == again, "relationIds": sorted(x for x in first if x)}


def planned_change(state):
    def apply(repo):
        payload = {
            "schemaVersion": 1, "id": "probe-missing-evidence",
            "intent": "Probe how a missing evidence path is reported.",
            "scope": ["shop.api"],
            "evidence": [{"element": "shop.api", "path": "tests/test_missing_probe.py", "state": state,
                          "note": "Deliberately absent probe path."}],
        }
        path = repo / "c4spec" / "changes" / "probe-missing-evidence.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path
    return apply


results = [
    probe("E-comment-only", append_comment,
          lambda delta, doc, row: delta == {"elements": 0, "relationships": 0, "views": 0}
          and row["reviewFingerprint"] != self_review
          and row["modelFingerprint"] == self_diff["fingerprint"]),
    probe("F-selector-order", reorder_selector,
          lambda delta, doc, row: delta["elements"] == 0 and delta["relationships"] == 0),
    probe("G-reversed-direction", reverse_direction,
          lambda delta, doc, row: delta["relationships"] >= 2),
    probe("H-parallel-relation", add_parallel,
          lambda delta, doc, row: delta["relationships"] == 1, extra=parallel_ids),
]

# I: planned and declared references to a path that does not exist.
for state in ("planned", "declared"):
    R.git(REPO, "checkout", "-q", "base")
    R.git(REPO, "checkout", "-q", "-B", f"probe-i-{state}", "base")
    change_path = planned_change(state)(REPO)
    head_sha = commit_all(f"probe evidence {state}")
    head_export, head_prov = compile_side(f"probe-i-{state}", head_sha)
    check_args = [sys.executable, str(R.SKILL / "check.py"), "--change", str(change_path),
                  "--model-json", str(head_export), "--project", R.project_id(head_export),
                  "--repo-root", str(REPO)]
    proposal = R.run(check_args + ["--phase", "proposal"], check=False)
    completion = R.run(check_args + ["--phase", "completion"], check=False)
    document = json.loads(proposal.stdout) if proposal.stdout.strip() else {}
    results.append({
        "probe": f"I-{state}-missing-path", "head": head_sha,
        "proposalExit": proposal.returncode, "completionExit": completion.returncode,
        "codes": sorted({f["code"] for f in document.get("findings", [])}),
        "pass": (proposal.returncode == 0 and "planned_path" in {f["code"] for f in document.get("findings", [])}
                 if state == "planned" else proposal.returncode == 1
                 and "missing_path" in {f["code"] for f in document.get("findings", [])}),
    })
    results[-1]["completionCodes"] = sorted({f["code"] for f in json.loads(completion.stdout).get("findings", [])}) \
        if completion.stdout.strip() else []

summary = {"work": str(work), "selfReviewFingerprint": self_review, "results": results,
           "failed": [row["probe"] for row in results if not row["pass"]]}
(WORK / "probes.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
raise SystemExit(1 if summary["failed"] else 0)
