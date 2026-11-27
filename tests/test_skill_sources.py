from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".agents" / "skills"
MODEL_FIRST = SKILLS / "c4spec-propose/references/model-first.md"
SKILL_NAMES = (
    "c4spec", "c4spec-apply", "c4spec-continue", "c4spec-explore",
    "c4spec-finish", "c4spec-maintain", "c4spec-propose", "c4spec-review", "c4spec-verify",
)


class SkillSourceTests(unittest.TestCase):
    def test_skill_identity_and_license(self):
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter = text.split("---\n", 2)[1].splitlines()
                self.assertIn(f"name: {name}", frontmatter)
                self.assertIn("license: Apache-2.0", frontmatter)

    def test_skill_installer_license(self):
        upstream = (ROOT / "licenses" / "Skills-MIT.txt").read_text(encoding="utf-8")
        audit = (ROOT / "docs" / "upstream-reuse.md").read_text(encoding="utf-8")
        self.assertIn("MIT License", upstream)
        self.assertIn("Vercel", upstream)
        self.assertIn("licenses/Skills-MIT.txt", audit)

    def test_standalone_skills_include_their_license(self):
        apache = (ROOT / "LICENSE").read_bytes()
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                directory = SKILLS / name
                self.assertEqual((directory / "LICENSE").read_bytes(), apache)
                notice = (directory / "NOTICE").read_text(encoding="utf-8")
                self.assertIn("Copyright 2026 C4Spec contributors", notice)

    def test_owned_likec4_bundle_is_self_contained_and_attributed(self):
        guide = SKILLS / "c4spec/references/likec4"
        index = (guide / "README.md").read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", index):
            with self.subTest(reference=target):
                self.assertTrue((guide / target).exists(), target)
        self.assertEqual((guide / "LICENSE.txt").read_bytes(),
                         (ROOT / "licenses/LikeC4-MIT.txt").read_bytes())
        self.assertIn("Denis Davydkov", (guide / "LICENSE.txt").read_text())
        self.assertIn("9a57883c1022d7ee44a29d8f2f9b7e94025cb4a7", index)
        # Consumers install one shared contract, not another discoverable skill.
        self.assertEqual(list(guide.rglob("SKILL.md")), [])
        self.assertNotRegex(index, r"(?:npx|bunx) (?:--yes )?likec4@latest")

    def test_workflow_guidance_lives_with_the_extended_skills(self):
        shared = (SKILLS / "c4spec" / "SKILL.md").read_text(encoding="utf-8")
        model_first = MODEL_FIRST.read_text(encoding="utf-8")
        maintain = (SKILLS / "c4spec-maintain/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("c4spec-maintain", shared)
        for name in SKILL_NAMES:
            if name not in {"c4spec", "c4spec-maintain"}:
                self.assertNotIn(f"`{name}`", shared + maintain)
        self.assertIn("c4spec-continue", model_first)
        self.assertIn("c4spec/constraints.json", model_first)

    def test_behavior_only_proposal_requires_no_architecture_edit(self):
        propose = (SKILLS / "c4spec-propose" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("zero C4 delta", propose)
        self.assertIn("native `diff` block", propose)
        self.assertIn("1.61.0", propose)
        self.assertIn("leave\n  the model as it is", propose)

    def test_project_local_layout_is_respected_without_new_config(self):
        shared = (SKILLS / "c4spec" / "SKILL.md").read_text(encoding="utf-8")
        propose = (SKILLS / "c4spec-propose" / "SKILL.md").read_text(encoding="utf-8")
        resume = (SKILLS / "c4spec-continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("AGENTS.md", shared)
        self.assertIn("existing model layout", propose)
        self.assertIn("likec4 diff list --json", resume)
        model_first = MODEL_FIRST.read_text(encoding="utf-8")
        self.assertIn("No per-change JSON file is required", model_first)
        self.assertIn("Use a per-change JSON record only", propose)
        self.assertIn("--constraints-file", model_first)

    def test_agent_neutral_resume_does_not_invent_slash_command(self):
        resume = (SKILLS / "c4spec-continue" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("/c4spec-continue", resume)
        self.assertIn("discoverable instructions", resume)

    def test_finish_never_merges_unimplemented_design_as_current(self):
        finish = (SKILLS / "c4spec-finish" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("only planned", finish)
        self.assertIn("design proposal, not merge-ready", finish)
        self.assertIn("human owner decides", finish)

    def test_structural_validation_is_not_test_execution(self):
        model_first = MODEL_FIRST.read_text(encoding="utf-8")
        verify = (SKILLS / "c4spec-verify" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("never executes tests", model_first)
        self.assertIn("check.py --phase completion", verify)
        self.assertIn("unverified requirements", verify)



if __name__ == "__main__":
    unittest.main()
