"""Custody invariants for the native-diff workflow (token separation).

Stdlib-only on purpose: the security property is that the job which executes
pull-request code holds no write permission, and the job holding the write
permission executes no pull-request code. These checks fail if that split is
undone or silently blurred.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "native-diff.yml"
DIFF_WORKFLOW = ROOT / ".github" / "workflows" / "pr-model-diff.yml"
SAME_REPO = "if: github.event.pull_request.head.repo.full_name == github.repository"
PERMISSION_LINE = re.compile(r"^ +([a-z-]+): (read|write|none)$", flags=re.M)
STEP = re.compile(
    r"^      - (?:name|uses): (?P<label>.*)\n(?P<body>(?:        [^\n]*\n|\n)*)",
    flags=re.M,
)
# Variables the runner provides without any `env:` mapping in the step.
RUNNER_PROVIDED = {"RUNNER_TEMP", "GITHUB_REPOSITORY", "GITHUB_RUN_ID",
                   "GITHUB_STEP_SUMMARY", "GITHUB_WORKSPACE", "GITHUB_SHA", "GITHUB_OUTPUT"}


def jobs(text: str) -> dict[str, str]:
    parts = re.split(r"^  (?P<name>[a-z0-9-]+):[ \t]*$", text, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def permissions(block: str) -> set[tuple[str, str]]:
    return set(PERMISSION_LINE.findall(block))


class NativeDiffWorkflowCustodyTests(unittest.TestCase):
    def setUp(self):
        self.rehearsal = WORKFLOW.read_text(encoding="utf-8")
        self.workflow = DIFF_WORKFLOW.read_text(encoding="utf-8")
        self.prepare = jobs(self.workflow)["prepare"]
        self.publish = jobs(self.workflow)["publish"]

    def test_rehearsal_is_read_only_and_publishes_only_actions_evidence(self):
        self.assertEqual(permissions(self.rehearsal), {("contents", "read")})
        self.assertNotIn("GH_TOKEN", self.rehearsal)
        self.assertIn("persist-credentials: false", self.rehearsal)
        self.assertIn('>> "$GITHUB_STEP_SUMMARY"', self.rehearsal)
        self.assertIn("inline_diff.py", self.rehearsal)
        self.assertIn("name: native-diff-as-is-changes-to-be", self.rehearsal)
        self.assertIn("retention-days: 7", self.rehearsal)
        self.assertNotIn("add likec4/likec4", self.rehearsal)
        self.assertIn("c4spec/references/likec4", self.rehearsal)
        self.assertIn("validate --json --no-layout", self.rehearsal)
        self.assertIn("likec4@1.61.0 --version", self.rehearsal)

    def test_preparer_is_read_only_and_runs_for_forks_and_reverts(self):
        preamble = self.workflow.split("\njobs:", 1)[0]
        self.assertEqual(permissions(preamble), {("contents", "read")})
        self.assertIn("\n  pull_request:\n", preamble)
        self.assertNotIn("pull_request_target", preamble)
        self.assertNotIn("paths:", preamble)
        self.assertIn("synchronize", preamble)
        self.assertFalse(permissions(self.prepare))
        self.assertNotRegex(self.prepare, r"(?m)^    if:")
        upload_steps = [body for label, body in STEP.findall(self.prepare)
                        if label.startswith("actions/upload-artifact@")]
        handoff = next(step for step in upload_steps if "name: c4spec-pr-model-diff\n" in step)
        pngs = next(step for step in upload_steps if "name: c4spec-rendered-diagrams\n" in step)
        self.assertIn(SAME_REPO, handoff)
        self.assertNotIn(SAME_REPO, pngs)
        self.assertIn("fetch-depth: 0", self.prepare)
        self.assertIn("persist-credentials: false", self.prepare)
        self.assertNotIn("github.token", self.prepare)
        self.assertIn("scripts/pr_model_diff.py", self.prepare)

    def test_publisher_handles_only_data_for_a_same_repository_event(self):
        self.assertIn(SAME_REPO, self.publish)
        self.assertIn("needs: prepare", self.publish)
        self.assertEqual(permissions(self.publish), {("pull-requests", "write")})
        for token in ("actions/checkout", "python3", "scripts/"):
            self.assertNotIn(token, self.publish)
        self.assertEqual(self.workflow.count("name: c4spec-pr-model-diff"), 2)

    def test_publisher_validates_event_and_only_mutates_the_current_pr_comment(self):
        for field in (".repo == $repo", ".head == $head", ".base == $base",
                      ".pr == $pr", ".runId == $run", ".commentBytes == $bytes"):
            self.assertIn(field, self.publish)
        self.assertIn('"$live" != "open $PR_BASE $PR_HEAD"', self.publish)
        self.assertIn('.user.login == "github-actions[bot]"', self.publish)
        self.assertIn('.body | startswith("<!-- c4spec-native-likec4-diff-review -->")', self.publish)
        self.assertIn('if [ "$bytes" -eq 0 ] && [ -z "$existing" ]; then', self.publish)
        self.assertIn('--method DELETE', self.publish)

    def test_steps_declare_every_variable_they_read(self):
        """set -u turns a missing step env mapping into a red run."""
        for job in (*jobs(self.workflow).values(), *jobs(self.rehearsal).values()):
            for label, body in STEP.findall(job):
                if "\n        run: |" not in body:
                    continue
                env_part, script = body.split("\n        run: |", 1)
                declared = set(re.findall(r"^ {10}([A-Z][A-Z0-9_]*): ", env_part, flags=re.M))
                used = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]*)", script))
                self.assertEqual(used - declared - RUNNER_PROVIDED, set(), label)


if __name__ == "__main__":
    unittest.main()
