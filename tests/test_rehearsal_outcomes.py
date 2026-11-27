"""Outcome checks for the four review cases, using offline inputs."""
import contextlib
import io
import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "prototype" / "m1-consumer-review"))
import rehearse  # noqa: E402


def row(**overrides):
    base = {
        "case": "A", "slug": "a", "title": "fake case", "compiler": "1.60.0", "compilerExit": 0,
        "reviewStatus": "source-bound-reverified", "views": [],
        "fingerprint": "sha256:" + "a" * 64, "reviewFingerprint": "sha256:" + "b" * 64,
        "proposalErrors": 0, "proposalWarnings": 0, "completionErrors": 0,
        "counts": {"elements": {"added": 1, "removed": 0, "modified": 0},
                   "relationships": {"added": 1, "removed": 0, "modified": 0},
                   "views": {"added": 1, "removed": 0, "modified": 0}},
        "proposalExit": 0, "proposalErrorCodes": [], "proposalWarningCodes": [],
        "completionExit": 0, "completionErrorCodes": [],
        "renderExit": 0, "testsExit": 0, "testsRan": 4,
        "htmlBytes": 1000, "markdownBytes": 500,
    }
    base.update(overrides)
    return base


class OutcomeTests(unittest.TestCase):
    def expect(self):
        return {"delta": {"elements": 1, "relationships": 1, "views": 1},
                "proposalExit": 0, "proposalErrorCodes": [], "proposalWarningCodes": [],
                "completionExit": 0, "completionErrorCodes": [],
                "renderExit": 0, "testsExit": 0, "testsRan": 4}

    def test_clean_row_passes(self):
        self.assertEqual(rehearse.outcome_violations(row(), self.expect()), [])

    def test_expected_negative_completion_is_not_a_failure(self):
        expect = {"delta": {"elements": 0, "relationships": 0, "views": 0},
                  "proposalExit": 0, "proposalErrorCodes": [], "proposalWarningCodes": ["planned_path"],
                  "completionExit": 1, "completionErrorCodes": ["missing_path", "still_planned"],
                  "renderExit": 0, "testsExit": 0, "testsRan": 4}
        negative = row(counts={"elements": {"added": 0, "removed": 0, "modified": 0},
                              "relationships": {"added": 0, "removed": 0, "modified": 0},
                              "views": {"added": 0, "removed": 0, "modified": 0}},
                       proposalWarningCodes=["planned_path"],
                       completionExit=1, completionErrorCodes=["missing_path", "still_planned"])
        self.assertEqual(rehearse.outcome_violations(negative, expect), [])

    def test_silent_completion_regression_is_a_failure(self):
        expect = self.expect()
        expect.update({"completionExit": 1, "completionErrorCodes": ["still_planned"]})
        self.assertTrue(any("completion exit 0" in item
                            for item in rehearse.outcome_violations(row(), expect)))

    def test_unexpected_delta_is_a_failure(self):
        broken = row(counts={"elements": {"added": 0, "removed": 0, "modified": 0},
                             "relationships": {"added": 1, "removed": 0, "modified": 0},
                             "views": {"added": 1, "removed": 0, "modified": 0}})
        self.assertIn("delta elements=0 expected 1", rehearse.outcome_violations(broken, self.expect()))

    def test_render_and_test_failures_are_failures(self):
        self.assertTrue(any("render exit 1" in item
                            for item in rehearse.outcome_violations(row(renderExit=1), self.expect())))
        self.assertTrue(any("scenario tests exit 1" in item
                            for item in rehearse.outcome_violations(row(testsExit=1), self.expect())))
        self.assertTrue(any("ran 0" in item
                            for item in rehearse.outcome_violations(row(testsRan=0), self.expect())))

    def test_assurance_and_artifacts_are_checked(self):
        self.assertTrue(any("reviewStatus" in item
                            for item in rehearse.outcome_violations(row(reviewStatus="exploratory"), self.expect())))
        self.assertTrue(any("packet" in item
                            for item in rehearse.outcome_violations(row(htmlBytes=0), self.expect())))
        self.assertTrue(any("compiler" in item
                            for item in rehearse.outcome_violations(row(compiler="1.59.4"), self.expect())))

    def test_warning_code_drift_is_a_failure(self):
        expect = self.expect()
        expect["proposalWarningCodes"] = ["planned_path"]
        self.assertTrue(any("warning codes" in item
                            for item in rehearse.outcome_violations(row(), expect)))


class ContractTests(unittest.TestCase):
    """The acceptance contract cannot be disabled by removing or emptying it."""

    def case(self, expect):
        document = {"slug": "x", "id": "X", "title": "t", "changeRevision": "head", "checkModel": "head"}
        if expect is not None:
            document["expect"] = expect
        return document

    def full_expect(self):
        return {"delta": {"elements": 0, "relationships": 0, "views": 0},
                "proposalExit": 0, "proposalErrorCodes": [], "proposalWarningCodes": [],
                "completionExit": 0, "completionErrorCodes": [],
                "renderExit": 0, "testsExit": 0, "testsRan": 1}

    def test_missing_expect_is_refused(self):
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.check_contract(self.case(None))

    def test_empty_expect_is_refused(self):
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.check_contract(self.case({}))

    def test_partial_expect_is_refused(self):
        partial = self.full_expect()
        partial.pop("renderExit")
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.check_contract(self.case(partial))

    def test_unknown_expect_key_is_refused(self):
        with_extra = self.full_expect()
        with_extra["renderExitCode"] = 0
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.check_contract(self.case(with_extra))

    def test_delta_must_declare_three_sections(self):
        broken = self.full_expect()
        broken["delta"] = {"elements": 0}
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.check_contract(self.case(broken))

    def test_complete_expect_passes(self):
        rehearse.check_contract(self.case(self.full_expect()))


class CompilerObservationTests(unittest.TestCase):
    """The compiler row must come from the CLI, not from the requested pin."""

    def stub(self, version, exit_code=0):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "likec4"
        path.write_text(f"#!/bin/sh\necho '{version}'\nexit {exit_code}\n")
        path.chmod(0o755)
        self.addCleanup(directory.cleanup)
        return str(path)

    def test_reported_version_is_observed(self):
        version, code = rehearse.compiler_version(self.stub("1.60.0"))
        self.assertEqual((version, code), ("1.60.0", 0))

    def test_wrong_cli_version_is_refused(self):
        version, code = rehearse.compiler_version(self.stub("1.59.4"))
        self.assertEqual(version, "1.59.4")
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.require_compiler_version(version, code)

    def test_failing_version_command_is_refused(self):
        version, code = rehearse.compiler_version(self.stub("1.60.0", exit_code=3))
        with self.assertRaises(rehearse.RehearsalError):
            rehearse.require_compiler_version(version, code)

    def test_mismatched_compiler_row_is_an_outcome_violation(self):
        broken = row(compiler="1.59.4", compilerExit=0)
        violations = rehearse.outcome_violations(broken, {
            "delta": {"elements": 1, "relationships": 1, "views": 1},
            "proposalExit": 0, "proposalErrorCodes": [], "proposalWarningCodes": [],
            "completionExit": 0, "completionErrorCodes": [],
            "renderExit": 0, "testsExit": 0, "testsRan": 4})
        self.assertTrue(any("compiler reported '1.59.4'" in item for item in violations))


class MainFailClosedTests(unittest.TestCase):
    """An unexpected outcome must make the whole rehearsal exit nonzero."""

    def test_unexpected_outcome_fails_the_run(self):
        def fake_case(case, work, keep):
            broken = row(case="A", renderExit=1, title="fake case", views=[])
            broken["violations"] = rehearse.outcome_violations(broken, case["expect"])
            return broken

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rehearse, "rehearsal_case", fake_case):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(rehearse.main(["--out", tmp, "--case", "A"]), 1)

    def test_expected_negative_completion_keeps_the_run_green(self):
        def fake_case(case, work, keep):
            expected = case["expect"]
            clean = row(case="A", title="fake case", views=[],
                        counts={"elements": {"added": 1, "removed": 0, "modified": 0},
                                "relationships": {"added": 1, "removed": 0, "modified": 0},
                                "views": {"added": 1, "removed": 0, "modified": 0}},
                        testsRan=expected["testsRan"])
            clean["violations"] = rehearse.outcome_violations(clean, expected)
            return clean

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rehearse, "rehearsal_case", fake_case):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(rehearse.main(["--out", tmp, "--case", "A"]), 0)


if __name__ == "__main__":
    unittest.main()
