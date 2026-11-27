#!/usr/bin/env python3
"""Four-case consumer rehearsal for the C4Spec skill chain.

Each case builds a disposable Git repository from ``examples/mini-project``,
applies a small declarative edit set, commits a base and a head revision, and
then runs the real chain: LikeC4 validate/export (pinned 1.60.0), provenance,
source-bound diff, proposal/completion check, and the offline review packet.

Nothing here is committed: every artifact lands under ``--out`` (scratch).
The case manifests are data, not a second model: an edit must match the base
text exactly or the rehearsal fails instead of quietly drifting.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent.parent
MINI = ROOT / "examples" / "mini-project"
SKILL = ROOT / ".agents" / "skills" / "c4spec" / "scripts"
CASES = Path(__file__).resolve().parent / "cases"
LIKE4C4 = os.environ.get("LIKE4C4", "likec4")
COMPILER_VERSION = os.environ.get("LIKEC4_VERSION", "1.60.0")
DEFAULT_CONFIG = {"name": "mini-shop"}
SUPPORTED_CONTRACT = {"changeRevision": "head", "checkModel": "head"}
EXPECT_KEYS = frozenset({"delta", "proposalExit", "proposalErrorCodes", "proposalWarningCodes",
                         "completionExit", "completionErrorCodes", "renderExit", "testsExit", "testsRan"})
DELTA_KEYS = frozenset({"elements", "relationships", "views"})


class RehearsalError(RuntimeError):
    pass


def run(command, cwd=None, check=True):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RehearsalError(f"{' '.join(map(str, command))} failed ({result.returncode}): "
                             f"{(result.stderr or result.stdout).strip()[:400]}")
    return result


def git(repo, *args, check=True):
    return run(["git", "-C", str(repo), *args], check=check)


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def copy_base(destination, config=None):
    """The LikeC4 config is a declared fixture, not an implicit harness detail."""
    shutil.copytree(MINI, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    write_json(destination / "architecture" / "likec4.config.json", config or DEFAULT_CONFIG)


def apply_case(repo, case):
    for edit in case.get("edits", []):
        path = repo / edit["path"]
        text = path.read_text(encoding="utf-8")
        if "find" in edit:
            occurrences = text.count(edit["find"])
            if occurrences != 1:
                raise RehearsalError(f"{case['slug']}: anchor in {edit['path']} matched {occurrences} times")
            text = text.replace(edit["find"], edit["replace"], 1)
        if "append" in edit:
            text = text.rstrip("\n") + "\n" + edit["append"].rstrip("\n") + "\n"
        path.write_text(text, encoding="utf-8")
    for target, source in case.get("files", {}).items():
        source_path = (CASES / case["slug"] / source)
        destination = repo / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)
    for target in case.get("delete", []):
        (repo / target).unlink()


VERSION = re.compile(r"\b(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)")


def compiler_version(cli=None):
    """Run the CLI and return (observed version or '', exit code)."""
    command = cli or LIKE4C4
    result = run([command, "--version"], check=False)
    text = (result.stdout or "").strip() or (result.stderr or "").strip()
    match = VERSION.search(text)
    return (match.group(1) if match else ""), result.returncode


def require_compiler_version(observed, exit_code):
    if exit_code != 0 or observed != COMPILER_VERSION:
        raise RehearsalError(f"requested LikeC4 {COMPILER_VERSION} but the CLI reported "
                             f"{observed or '<none>'} (exit {exit_code}); refusing to record evidence")


def likec4(*args, cwd, check=True):
    return run([LIKE4C4, *args], cwd=cwd, check=check)


def project_id(export_path):
    document = json.loads(export_path.read_text(encoding="utf-8"))
    project = document[0] if isinstance(document, list) else document
    return project.get("projectId")


def outcome_violations(row, expect):
    """Every unexpected outcome is a failure; an expected negative completion is not."""
    problems = []
    totals = {section: sum(row["counts"][section].values()) for section in ("elements", "relationships", "views")}
    for section, expected in expect["delta"].items():
        if totals[section] != expected:
            problems.append(f"delta {section}={totals[section]} expected {expected}")
    if row["proposalExit"] != expect["proposalExit"]:
        problems.append(f"proposal exit {row['proposalExit']} expected {expect['proposalExit']}")
    if sorted(row["proposalErrorCodes"]) != sorted(expect["proposalErrorCodes"]):
        problems.append(f"proposal error codes {row['proposalErrorCodes']} expected {expect['proposalErrorCodes']}")
    if sorted(row["proposalWarningCodes"]) != sorted(expect["proposalWarningCodes"]):
        problems.append(f"proposal warning codes {row['proposalWarningCodes']} expected {expect['proposalWarningCodes']}")
    if row["completionExit"] != expect["completionExit"]:
        problems.append(f"completion exit {row['completionExit']} expected {expect['completionExit']}")
    if sorted(row["completionErrorCodes"]) != sorted(expect["completionErrorCodes"]):
        problems.append(f"completion error codes {row['completionErrorCodes']} expected {expect['completionErrorCodes']}")
    if row["renderExit"] != expect["renderExit"]:
        problems.append(f"render exit {row['renderExit']} expected {expect['renderExit']}")
    if row["testsExit"] != expect["testsExit"]:
        problems.append(f"scenario tests exit {row['testsExit']} expected {expect['testsExit']}")
    if row["testsRan"] != expect["testsRan"]:
        problems.append(f"scenario tests ran {row['testsRan']} expected {expect['testsRan']}")
    if row["reviewStatus"] != "source-bound-reverified":
        problems.append(f"reviewStatus {row['reviewStatus']!r} expected 'source-bound-reverified'")
    if not row["htmlBytes"] or not row["markdownBytes"]:
        problems.append("review packet HTML/Markdown missing or empty")
    if row.get("compilerExit") != 0:
        problems.append(f"compiler --version exit {row.get('compilerExit')} expected 0")
    if row["compiler"] != COMPILER_VERSION:
        problems.append(f"compiler reported {row['compiler']!r} expected {COMPILER_VERSION!r}")
    return problems


def check_contract(case):
    expect = case.get("expect")
    if not isinstance(expect, dict) or not expect:
        raise RehearsalError(f"{case['slug']}: no 'expect' block; the rehearsal refuses to run without acceptance criteria")
    missing = sorted(EXPECT_KEYS - set(expect))
    extra = sorted(set(expect) - EXPECT_KEYS)
    if missing or extra:
        raise RehearsalError(f"{case['slug']}: expect block incomplete or unknown — missing {missing}, unknown {extra}")
    delta = expect["delta"]
    if not isinstance(delta, dict) or set(delta) != DELTA_KEYS:
        raise RehearsalError(f"{case['slug']}: expect.delta must declare exactly {sorted(DELTA_KEYS)}")
    for key, expected in SUPPORTED_CONTRACT.items():
        declared = case.get(key, expected)
        if declared != expected:
            raise RehearsalError(f"{case['slug']}: this harness only implements {key}={expected!r}, "
                                 f"manifest asks for {declared!r}")


def rehearsal_case(case, work, keep):
    slug = case["slug"]
    check_contract(case)
    observed_version, version_exit = compiler_version()
    require_compiler_version(observed_version, version_exit)
    root = work / slug
    repo = root / "repo"
    artifacts = root / "artifacts"
    repo.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    copy_base(repo, case.get("likec4Config"))
    git(repo, "init", "-q", "-b", "base")
    git(repo, "config", "user.email", "rehearsal@example.invalid")
    git(repo, "config", "user.name", "C4Spec rehearsal")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    model = repo / "architecture"
    base_export = artifacts / "model-base.json"
    likec4("validate", "--json", "--no-layout", "architecture", cwd=repo)
    likec4("export", "json", "--skip-layout", "architecture", "-o", str(base_export), cwd=repo)
    run([sys.executable, str(SKILL / "provenance.py"), "--model-dir", "architecture",
         "--export", str(base_export), "--git-commit", base_sha, "--compiler-version", observed_version,
         "--compiler-command", f"{LIKE4C4} --version", "--out", str(artifacts / "prov-base.json")], cwd=repo)

    apply_case(repo, case)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", case["title"])
    head_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    head_export = artifacts / "model-head.json"
    validate_head = likec4("validate", "--json", "--no-layout", "architecture", cwd=repo)
    write_json(artifacts / "validate-head.json", json.loads(validate_head.stdout))
    likec4("export", "json", "--skip-layout", "architecture", "-o", str(head_export), cwd=repo)
    run([sys.executable, str(SKILL / "provenance.py"), "--model-dir", "architecture",
         "--export", str(head_export), "--git-commit", head_sha, "--compiler-version", observed_version,
         "--compiler-command", f"{LIKE4C4} --version", "--out", str(artifacts / "prov-head.json")], cwd=repo)

    project = project_id(head_export)
    diff_path = artifacts / "diff.json"
    change_path = repo / case["change"] if case.get("change") else None
    diff_args = [sys.executable, str(SKILL / "diff.py"), "--base", str(base_export), "--head", str(head_export),
                 "--project", project, "--base-provenance", str(artifacts / "prov-base.json"),
                 "--head-provenance", str(artifacts / "prov-head.json"), "--base-ref", base_sha,
                 "--head-ref", head_sha, "--repo-root", str(repo)]
    if change_path is not None:
        diff_args += ["--change", str(change_path)]
    diff = run(diff_args)
    write_json(diff_path, json.loads(diff.stdout))
    check_args = [sys.executable, str(SKILL / "check.py"), "--model-json", str(head_export),
                  "--project", project, "--repo-root", str(repo)]
    if change_path is not None:
        check_args += ["--change", str(change_path)]
    proposal = run(check_args + ["--phase", "proposal"], check=False)
    completion = run(check_args + ["--phase", "completion"], check=False)
    (artifacts / "check-proposal.json").write_text(proposal.stdout, encoding="utf-8")
    (artifacts / "check-completion.json").write_text(completion.stdout, encoding="utf-8")

    png_dir = artifacts / "png"
    png_dir.mkdir(exist_ok=True)
    for view in case.get("views", []):
        likec4("export", "png", "--filter", view, "--flat", "-o", str(png_dir), "architecture", cwd=repo)

    render_args = [sys.executable, str(SKILL / "render_review.py"), "--diff", str(diff_path),
                   "--check", str(artifacts / "check-proposal.json"),
                   "--html", str(root / "review.html"), "--markdown", str(root / "review.md")]
    if change_path is not None:
        render_args += ["--change", str(change_path)]
    for view in case.get("views", []):
        render_args += ["--render", f"{view}={png_dir / (view + '.png')}"]
    render = run(render_args, check=False)

    tests = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo, check=False)
    test_match = re.search(r"Ran (\d+) tests?", tests.stderr + tests.stdout)
    tests_ran = int(test_match.group(1)) if test_match else 0

    report = json.loads(diff_path.read_text(encoding="utf-8"))
    counts = {section: {op: len(report[section][op]) for op in ("added", "removed", "modified")}
              for section in ("elements", "relationships", "views")}
    proposal_doc = json.loads(proposal.stdout) if proposal.stdout.strip() else {}
    completion_doc = json.loads(completion.stdout) if completion.stdout.strip() else {}
    render_doc = json.loads(render.stdout) if render.stdout.strip() else {}
    row = {
        "case": case["id"], "slug": slug, "title": case["title"],
        "compiler": observed_version, "compilerExit": version_exit,
        "base": base_sha, "head": head_sha, "project": project,
        "valid_head": json.loads(validate_head.stdout).get("valid"),
        "counts": counts,
        "fingerprint": report.get("fingerprint"), "reviewFingerprint": report.get("reviewFingerprint"),
        "reviewStatus": report.get("reviewStatus"),
        "assurance": report.get("reviewAssurance"),
        "proposalExit": proposal.returncode,
        "proposalErrors": proposal_doc.get("errors"), "proposalWarnings": proposal_doc.get("warnings"),
        "proposalErrorCodes": sorted({f["code"] for f in proposal_doc.get("findings", []) if f["severity"] == "error"}),
        "proposalWarningCodes": sorted({f["code"] for f in proposal_doc.get("findings", []) if f["severity"] == "warning"}),
        "completionExit": completion.returncode, "completionErrors": completion_doc.get("errors"),
        "completionErrorCodes": sorted({f["code"] for f in completion_doc.get("findings", []) if f["severity"] == "error"}),
        "testsExit": tests.returncode, "testsRan": tests_ran,
        "renderExit": render.returncode,
        "renderWarnings": render_doc.get("warnings"),
        "htmlBytes": (root / "review.html").stat().st_size if (root / "review.html").exists() else 0,
        "markdownBytes": (root / "review.md").stat().st_size if (root / "review.md").exists() else 0,
        "views": case.get("views", []),
        "packet": str(root / "review.html"),
        "markdown": str(root / "review.md"),
    }
    row["violations"] = outcome_violations(row, case["expect"])
    if proposal.returncode not in (0, 1):
        row["proposalStderr"] = proposal.stderr.strip()[:300]
    if render.returncode != 0:
        row["renderStderr"] = render.stderr.strip()[:300]
    if not keep:
        shutil.rmtree(repo, ignore_errors=True)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="artifact directory (default: a fresh temp directory)")
    parser.add_argument("--case", action="append", default=[], help="only this case id (repeatable)")
    parser.add_argument("--keep-repos", action="store_true", help="keep the disposable Git repositories")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="m1-rehearsal-"))
    out.mkdir(parents=True, exist_ok=True)
    manifests = sorted(p for p in CASES.glob("*.json"))
    if not manifests:
        print("no case manifests found", file=sys.stderr)
        return 2
    rows, failures = [], []
    for manifest in manifests:
        case = json.loads(manifest.read_text(encoding="utf-8"))
        if args.case and case["id"] not in args.case:
            continue
        print(f"case {case['id']}: {case['title']}", file=sys.stderr)
        try:
            row = rehearsal_case(case, out, args.keep_repos)
            rows.append(row)
            for violation in row.get("violations", []):
                failures.append({"case": case["id"], "error": "unexpected outcome: " + violation})
        except (RehearsalError, OSError, subprocess.SubprocessError) as exc:
            failures.append({"case": case["id"], "error": str(exc)})
            print(f"  failed: {exc}", file=sys.stderr)
    matrix = {"out": str(out), "compiler": COMPILER_VERSION, "cases": rows, "failures": failures,
              "generated": "scratch only; nothing here is committed"}
    write_json(out / "matrix.json", matrix)
    lines = ["| Case | Delta (E/R/V) | Views added | model-only | review | proposal | completion | packet |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        delta = "/".join(str(sum(row["counts"][section].values())) for section in ("elements", "relationships", "views"))
        lines.append(f"| {row['case']} {row['title']} | {delta} | {', '.join(row['views']) or '—'} | "
                     f"`{str(row['fingerprint'])[:19]}…` | `{str(row['reviewFingerprint'])[:19]}…` | "
                     f"exit {row['proposalExit']} ({row['proposalErrors']}e/{row['proposalWarnings']}w) | "
                     f"exit {row['completionExit']} ({row['completionErrors']}e) | "
                     f"{row['htmlBytes']} B |")
    for failure in failures:
        lines.append(f"| {failure['case']} | FAILED | — | — | — | — | — | `{failure['error'][:120]}` |")
    (out / "matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "cases": [r["case"] for r in rows], "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
