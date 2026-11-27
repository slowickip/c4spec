#!/usr/bin/env python3
"""Exercise native LikeC4 model diffs without keeping a second architecture model.

Reads the canonical mini-project shop.c4, creates disposable proposal and
apply worktrees, and executes the repository's lockfile-installed LikeC4 CLI. Never writes to
the authoritative source. Run on a new Git branch to review proposed diffs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "examples/mini-project/architecture/shop.c4"
CLI = ROOT / "node_modules/.bin/likec4"
DIFF_NAME = "replaceNotifications"
DIFF = """
// Native, unapproved architecture proposal. The model above remains AS-IS.
diff replaceNotifications 'Replace the notification consumer' {
  description 'Introduce a separately deployed V2 worker while retiring the old worker'

  remove {
    shop.worker
  }

  add {
    extend shop {
      workerV2 = container 'Notification Worker V2' {
        technology 'Python (queue consumer)'
        description 'Consumes notification events with bounded retries and idempotent delivery'
      }
    }
    shop.broker -> shop.workerV2 'Delivers notification events' 'AMQP'
    shop.workerV2 -> customer 'Sends notifications' 'email'
  }
}
"""


def proposal_source(original: str) -> str:
    """Only the view selectors change; the current model nodes do not."""
    anchors = (
        "include customer, shop.api, shop.db, shop.broker, shop.worker",
        "include customer, shop.api, shop.broker, shop.worker",
    )
    for anchor in anchors:
        if original.count(anchor) != 1:
            raise ValueError(f"Expected exactly one view selector: {anchor}")
        original = original.replace(anchor, anchor + ", shop.workerV2")
    if "diff replaceNotifications" in original:
        raise ValueError("Demo diff unexpectedly exists in canonical source")
    return original.rstrip() + "\n" + DIFF


def run(cwd: Path, *args: str, expected: int | None = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(CLI), *args], cwd=cwd, text=True, capture_output=True, check=False, timeout=180
    )
    if expected is not None and result.returncode != expected:
        raise AssertionError(
            f"{cwd.name}: {' '.join(args)} returned {result.returncode}, "
            f"expected {expected}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def source_file(directory: Path) -> Path:
    return directory / "architecture/shop.c4"


def write(directory: Path, text: str) -> None:
    target = source_file(directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, help="New scratch directory for proposal, applied and negative fixtures"
    )
    args = parser.parse_args()
    output = args.out.resolve() if args.out else Path(tempfile.mkdtemp(prefix="c4spec-native-diff-"))
    # Never accidentally modify a model in the tool checkout.
    if output == ROOT or ROOT in output.parents:
        parser.error("--out must be outside the C4Spec repository")
    if output.exists() and any(output.iterdir()):
        parser.error("--out must be a new or empty scratch directory")
    output.mkdir(parents=True, exist_ok=True)

    original = SOURCE.read_text(encoding="utf-8")
    proposal = proposal_source(original)
    proposal_dir = output / "proposal"
    applied_dir = output / "applied"
    invalid_dir = output / "stale-reference"
    overlap_dir = output / "overlapping"
    write(proposal_dir, proposal)
    observed_version = run(proposal_dir, "--version").stdout.strip()
    expected_version = json.loads((ROOT / "package.json").read_text())["dependencies"]["likec4"]
    if observed_version != expected_version:
        raise AssertionError(f"Expected LikeC4 {expected_version}, got {observed_version!r}")

    run(proposal_dir, "validate")
    diff_list = run(proposal_dir, "diff", "list", "--json").stdout
    if DIFF_NAME not in diff_list:
        raise AssertionError(f"Native diff absent from LikeC4 diff list: {diff_list}")
    # Require the official CLI to report actual before/after view changes,
    # not merely parse the DSL. This is the provider's reported impact, not
    # C4Spec's second model or an invented inferred visual diff.
    listed = json.loads(diff_list)
    if not isinstance(listed, list):
        raise AssertionError("LikeC4 diff list did not return an array")
    matches = [d for d in listed if d.get("id") == DIFF_NAME]
    if len(matches) != 1:
        raise AssertionError("Expected one exactly matching native diff")
    listed_diff = matches[0]
    if listed_diff.get("added", {}).get("elements") != 1:
        raise AssertionError("The intended V2 worker is not reported as added")
    if listed_diff.get("removed", {}).get("elements") != 1:
        raise AssertionError("The legacy worker is not reported as removed")
    views = {v.get("id"): v for v in listed_diff.get("views", [])}
    for view_id in ("shop-overview", "notifications"):
        view = views.get(view_id)
        if not view or view.get("nodes", {}).get("added") != 1 or view.get("nodes", {}).get("removed") != 1:
            raise AssertionError(f"Native red/green node delta missing in {view_id}")
        if view.get("edges", {}).get("added", 0) < 1 or view.get("edges", {}).get("removed", 0) < 1:
            raise AssertionError(f"Native red/green relationship delta missing in {view_id}")
    (output / "diff-list.json").write_text(
        json.dumps(listed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    proposal_hash = sha256(source_file(proposal_dir))
    preview = run(proposal_dir, "diff", "apply", DIFF_NAME, "--dry-run")
    (output / "dry-run.txt").write_text(preview.stdout + preview.stderr, encoding="utf-8")
    if sha256(source_file(proposal_dir)) != proposal_hash:
        raise AssertionError("Dry-run modified the proposal source")

    # Build a reviewable, self-contained As-is / Changes / To-be page.
    # Native LikeC4 embeds the named diff in its static build; unlike a
    # Mermaid export this preserves the interactive overlay.
    site_dir = output / "review-site"
    run(proposal_dir, "build", "--output", str(site_dir), "--output-single-file")
    review_html = site_dir / "index.html"
    if not review_html.is_file() or review_html.stat().st_size < 1024:
        raise AssertionError("LikeC4 did not generate an interactive single-file review")
    if sha256(source_file(proposal_dir)) != proposal_hash:
        raise AssertionError("Static build unexpectedly mutated the proposal source")

    shutil.copytree(proposal_dir, applied_dir)
    run(applied_dir, "diff", "apply", DIFF_NAME)
    run(applied_dir, "validate")
    applied = source_file(applied_dir).read_text(encoding="utf-8")
    if "diff replaceNotifications" in applied or "worker = container 'Notification Worker'" in applied:
        raise AssertionError("Apply left a proposed diff or the removed worker in the model")
    if "workerV2 = container 'Notification Worker V2'" not in applied:
        raise AssertionError("Apply did not install new worker")
    if "shop.worker " in applied or "shop.worker," in applied:
        raise AssertionError("Apply left a relationship or view selector to removed worker")
    for view in ("view shop-overview {", "view notifications {"):
        if view not in applied:
            raise AssertionError(f"Apply lost stable view ID {view}")
    if "replaceNotifications" in run(applied_dir, "diff", "list", "--json").stdout:
        raise AssertionError("Applied diff is still listed")

    # A stale proposed removal must not pass as a valid change.
    write(invalid_dir, proposal.replace("    shop.worker\n", "    shop.unknownWorker\n", 1))
    invalid = run(invalid_dir, "validate", expected=None)
    if invalid.returncode == 0:
        invalid = run(invalid_dir, "diff", "apply", DIFF_NAME, "--dry-run", expected=None)
    if invalid.returncode == 0:
        raise AssertionError("Stale removed node was silently accepted")

    # Two diffs removing the same element must not apply without explicit
    # --accept-overlaps. No such override is ever used by this rehearsal.
    second_diff = """
diff conflictingRemoval 'Conflicting worker retirement' {
  remove {
    shop.worker
  }
}
"""
    write(overlap_dir, proposal.rstrip() + "\n" + second_diff)
    run(overlap_dir, "validate")
    overlapping = run(overlap_dir, "diff", "apply", DIFF_NAME, expected=None)
    if overlapping.returncode == 0:
        raise AssertionError("Overlapping model diffs were applied without consent")

    summary = {
        "likec4Version": observed_version,
        "diff": DIFF_NAME,
        "source": str(SOURCE.relative_to(ROOT)),
        "proposal": str(source_file(proposal_dir)),
        "applied": str(source_file(applied_dir)),
        "reviewHtml": str(review_html),
        "reviewHtmlBytes": review_html.stat().st_size,
        "proposalSha256": proposal_hash,
        "appliedSha256": sha256(source_file(applied_dir)),
        "validatedProposal": True,
        "dryRunNonMutating": True,
        "appliedAndValidated": True,
        "staleRemovalRejected": True,
        "overlappingDiffRejected": True,
        "modelOnlySourcePreserved": sha256(SOURCE) == hashlib.sha256(original.encode()).hexdigest(),
        "note": "This is a scratch fixture, not an approved deployment or a production change.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
