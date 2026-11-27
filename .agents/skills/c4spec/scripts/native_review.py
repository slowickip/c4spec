#!/usr/bin/env python3
"""Review a committed native LikeC4 diff in scratch; check proposal/apply drift.

Never applies to the consuming checkout. Uses the existing compiler and C4Spec
source-manifest/comparison helpers. Generated packets are evidence, not approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from diff import compare, load
from provenance import (HEX40, collect_sources, git_toplevel, manifest_digest,
                        verify_git_sources)

VERSION = "1.61.0"
DEFAULT_CLI = f"npx --yes likec4@{VERSION}"


class InputError(ValueError):
    pass


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if result.returncode:
        raise InputError(result.stderr.strip() or "Git check failed")
    return result.stdout.strip()


def sources(repo, model_dir):
    repo = git_toplevel(repo)
    model = (repo / model_dir).resolve()
    if not model.is_relative_to(repo) or model == repo:
        raise InputError("model-dir must be a directory inside the repository")
    commit = git(repo, "rev-parse", "HEAD")
    manifest = collect_sources(model)
    relative = verify_git_sources(model, manifest, commit)
    return repo, model, relative, commit, manifest


def run_cli(cli, cwd, *args):
    result = subprocess.run([*shlex.split(cli), *args], cwd=cwd, text=True,
                            capture_output=True, timeout=300)
    if result.returncode:
        raise InputError(f"LikeC4 {' '.join(args)} failed ({result.returncode}):\n"
                         + (result.stdout + result.stderr)[-6000:])
    return result.stdout


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_sources(model, manifest, destination):
    for item in manifest:
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(model / item["path"], target)


def assert_unchanged(model, expected, label):
    if collect_sources(model) != expected:
        raise InputError(label + " changed model sources")


def review(repo, model_dir, name, base, out, cli=DEFAULT_CLI):
    repo, model, relative, commit, manifest = sources(repo, model_dir)
    if not HEX40.fullmatch(base or ""):
        raise InputError("base must be an exact 40-character Git commit")
    git(repo, "merge-base", "--is-ancestor", base, commit)
    if out.is_symlink():
        raise InputError("out must not be a symlink")
    out = out.resolve()
    if out == repo or out.is_relative_to(repo) or repo.is_relative_to(out):
        raise InputError("out must be outside the repository and not its ancestor")
    out.mkdir(parents=True, exist_ok=False)
    proposed, applied = out / "proposal", out / "applied"
    copy_sources(model, manifest, proposed)
    version = run_cli(cli, proposed, "--version").strip()
    if version != VERSION:
        raise InputError(f"Expected LikeC4 {VERSION}, got {version!r}")
    # diff list alone can exit 0 on invalid diff syntax. Validate first.
    run_cli(cli, proposed, "validate", "--json", "--no-layout", ".")
    listed = json.loads(run_cli(cli, proposed, "diff", "list", "--json", "."))
    if not isinstance(listed, list) or len(listed) != 1:
        raise InputError("Helper requires one pending native diff; isolate/reconcile other proposals before review")
    matches = [d for d in listed if d.get("id") == name]
    if len(matches) != 1:
        raise InputError("Expected exactly one native diff with this name/project")
    write_json(out / "diff-list.json", listed)
    dry_run = run_cli(cli, proposed, "diff", "apply", name, "--dry-run", ".")
    (out / "dry-run.txt").write_text(dry_run, encoding="utf-8")
    assert_unchanged(proposed, manifest, "Dry-run")
    (out / "source.patch").write_text(git(repo, "diff", base, commit, "--", relative) + "\n",
                                      encoding="utf-8")
    run_cli(cli, proposed, "export", "json", "--skip-layout", "-o", str(out / "as-is.json"), ".")
    run_cli(cli, proposed, "build", "--output", str(out / "review-site"), "--output-single-file", ".")
    if not (out / "review-site/index.html").is_file():
        raise InputError("LikeC4 did not produce review-site/index.html")
    assert_unchanged(proposed, manifest, "Export/build")
    shutil.copytree(proposed, applied)
    run_cli(cli, applied, "diff", "apply", name, ".")
    run_cli(cli, applied, "validate", "--json", "--no-layout", ".")
    remaining = json.loads(run_cli(cli, applied, "diff", "list", "--json", "."))
    if any(d.get("id") == name for d in remaining):
        raise InputError("Applied diff remains pending")
    run_cli(cli, applied, "export", "json", "--skip-layout", "-o", str(out / "to-be.json"), ".")
    delta = compare(load(out / "as-is.json"), load(out / "to-be.json"))
    write_json(out / "semantic-diff.json", delta)
    if not any(delta[section][action] for section in ("elements", "relationships", "views")
               for action in ("added", "removed", "modified")):
        raise InputError("Native proposal produces no supported semantic delta; inspect sources instead")
    assert_unchanged(model, manifest, "Review")
    if git(repo, "rev-parse", "HEAD") != commit:
        raise InputError("Repository HEAD moved during review")
    packet = {"schemaVersion": 1, "kind": "c4spec-native-review", "proposalCommit": commit,
              "baseCommit": base, "modelDir": relative, "diff": name, "likec4Version": VERSION,
              "sources": manifest, "sourcesDigest": manifest_digest(manifest),
              "expectedAppliedSources": collect_sources(applied),
              "nativeImpact": matches[0], "humanApprovalVerified": False,
              "testsExecuted": False, "runtimeVerified": False,
              "limitations": ["Unsigned local packet; not an approval or authenticated attestation",
                              "Only model directory .c4/.likec4 and LikeC4 config are copied; external imports/assets unsupported",
                              "Native HTML owns full visual review; computed semantic subset is advisory",
                              "Run implementation tests separately; scratch model apply is not implementation"]}
    write_json(out / "review.json", packet)
    lines = ["# Native LikeC4 proposal review", "", f"Proposal commit: `{commit}`",
             f"Base commit: `{base}`", f"Source manifest: `{packet['sourcesDigest']}`", "",
             "Open [As-is / Changes / To-be](review-site/index.html), then inspect `source.patch`.", "",
             "Native impact (provider output):", "", "```json", json.dumps(matches[0], indent=2), "```", "",
             "No human approval, implementation tests or runtime verification recorded.", ""]
    (out / "review.md").write_text("\n".join(lines), encoding="utf-8")
    return packet


def verify_packet(repo, model_dir, packet_path, applied=False, cli=DEFAULT_CLI):
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if packet.get("kind") != "c4spec-native-review" or packet.get("schemaVersion") != 1:
        raise InputError("Unsupported review packet")
    repo, model, relative, commit, manifest = sources(repo, model_dir)
    if relative != packet["modelDir"] or packet["likec4Version"] != VERSION:
        raise InputError("Model directory or compiler pin differs from review")
    if manifest_digest(packet["sources"]) != packet["sourcesDigest"]:
        raise InputError("Review source manifest is inconsistent")
    # Re-verify the reviewed source manifest against this repository's Git objects.
    from provenance import verify_sources_at_commit
    verify_sources_at_commit(repo, relative, packet["sources"], packet["proposalCommit"])
    if applied:
        if commit == packet["proposalCommit"]:
            raise InputError("Applied verification needs a committed descendant of the proposal")
        git(repo, "merge-base", "--is-ancestor", packet["proposalCommit"], commit)
        if manifest != packet["expectedAppliedSources"]:
            raise InputError("Applied sources diverge from the reviewed native result; re-review required")
    elif commit != packet["proposalCommit"] or manifest != packet["sources"]:
        raise InputError("Proposal commit/sources changed since review; re-review required")
    if run_cli(cli, model, "--version").strip() != VERSION:
        raise InputError("Compiler differs from review")
    run_cli(cli, model, "validate", "--json", "--no-layout", ".")
    listed = json.loads(run_cli(cli, model, "diff", "list", "--json", "."))
    if len(listed) != (0 if applied else 1):
        raise InputError("Pending diff set differs from this single-proposal review")
    present = any(d.get("id") == packet["diff"] for d in listed)
    if present == applied:
        raise InputError("Unexpected native diff state")
    assert_unchanged(model, manifest, "Verification")
    if git(repo, "rev-parse", "HEAD") != commit:
        raise InputError("Repository HEAD moved during verification")
    return {"valid": True, "mode": "applied" if applied else "proposal", "commit": commit,
            "humanApprovalVerified": False, "testsExecuted": False, "runtimeVerified": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    p.add_argument("--model-dir", default="architecture")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--diff", help="Named committed native proposal to review in scratch")
    mode.add_argument("--check-proposal", type=Path, help="review.json to check before an authorized apply")
    mode.add_argument("--check-applied", type=Path, help="review.json to compare with a committed applied result")
    p.add_argument("--base", help="Exact reviewed Git base SHA; required with --diff")
    p.add_argument("--out", type=Path, help="New scratch directory outside repository; required with --diff")
    p.add_argument("--likec4-command", default=DEFAULT_CLI)
    a = p.parse_args(argv)
    try:
        if a.diff:
            if not a.base or not a.out:
                p.error("--diff requires --base and --out")
            result = review(a.repo_root, a.model_dir, a.diff, a.base, a.out, a.likec4_command)
            print(json.dumps({"valid": True, "proposalCommit": result["proposalCommit"],
                              "review": str(a.out.resolve() / "review.json")}))
        else:
            print(json.dumps(verify_packet(a.repo_root, a.model_dir, a.check_applied or a.check_proposal,
                                           bool(a.check_applied), a.likec4_command)))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as ex:
        print(json.dumps({"valid": False, "error": str(ex)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
