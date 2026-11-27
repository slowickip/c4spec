from pathlib import Path
import os
import shutil
import sys
import tempfile
import subprocess
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from install import (  # noqa: E402
    InstallError,
    classify_skill_spot,
    create_skill_link,
    install,
    skill_link_text,
)

REPO = Path(__file__).resolve().parent.parent


def _symlink_supported() -> bool:
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "target"
        target.mkdir()
        link = Path(temp) / "link"
        try:
            os.symlink(target, link, True)
        except (OSError, NotImplementedError):
            return False
        return link.is_symlink()


class InstallTests(unittest.TestCase):
    def test_dry_run_and_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            dry = install(folder, dry_run=True)
            self.assertGreaterEqual(len(dry), 6)
            self.assertFalse((folder / ".agents").exists())
            actual = install(folder)
            self.assertTrue((folder / ".agents/skills/c4spec/SKILL.md").is_file())
            shared = folder / ".agents/skills/c4spec"
            self.assertTrue((shared / "scripts/check.py").is_file())
            self.assertTrue((shared / "schemas/change.schema.json").is_file())
            self.assertTrue((shared / "references/c4-governance.md").is_file())
            self.assertTrue((shared / "LICENSE").is_file())
            guide = shared / "references/likec4"
            for asset in ("README.md", "diffs.md", "LICENSE.txt",
                          "example/model.c4", "example/likec4.config.json"):
                self.assertTrue((guide / asset).is_file(), asset)

            example = REPO / "examples/mini-project/c4spec/changes/add-cache.json"
            result = subprocess.run([sys.executable, str(shared / "scripts/check.py"),
                                     "--change", str(example),
                                     "--repo-root", str(REPO / "examples/mini-project")],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(any(x[0] == "installed" for x in actual))
            repeat = install(folder)
            self.assertTrue(all(x[0] == "skipped-existing" for x in repeat))


@unittest.skipUnless(_symlink_supported(), "filesystem without symlink support")
class SkillLinkTests(unittest.TestCase):
    """Two agent conventions, the no-link fallback and a kept user edit."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        (self.root / ".claude").mkdir()
        (self.root / ".hermes").mkdir()

    def tearDown(self):
        self._temp.cleanup()

    def _shared(self, name="c4spec-propose"):
        return self.root / ".agents" / "skills" / name

    def test_claude_and_hermes_get_relative_links(self):
        actions = install(self.root, tools="auto")
        for tool in (".claude", ".hermes"):
            link = self.root / tool / "skills" / "c4spec-propose"
            self.assertTrue(link.is_symlink(), f"{tool} did not get a link")
            self.assertFalse(os.readlink(link).startswith("/"), "link must be relative")
            self.assertEqual(link.resolve(), self._shared().resolve())
            self.assertTrue((link / "SKILL.md").is_file())
        self.assertIn(("linked", "claude:c4spec-propose"), actions)
        self.assertIn(("linked", "hermes:c4spec-propose"), actions)
        # A tool that reads the shared folder itself gets no second copy.
        self.assertFalse((self.root / ".codex").exists())

    def test_links_survive_moving_the_project(self):
        install(self.root, tools="auto")
        moved = self.root.parent / (self.root.name + "-moved")
        shutil.move(str(self.root), str(moved))
        try:
            link = moved / ".claude" / "skills" / "c4spec-propose"
            self.assertTrue(link.is_symlink())
            self.assertTrue((link / "SKILL.md").is_file(), "relative link broke after a move")
        finally:
            shutil.move(str(moved), str(self.root))

    def test_rerun_is_idempotent(self):
        install(self.root, tools="auto")
        repeat = install(self.root, tools="auto")
        self.assertTrue(all(row[0] in {"skipped-existing", "already-linked"} for row in repeat),
                        repeat)

    def test_user_edit_is_kept_and_force_replaces_it(self):
        spot = self.root / ".claude" / "skills" / "c4spec-propose"
        spot.mkdir(parents=True)
        (spot / "SKILL.md").write_text("# my own notes\n", encoding="utf-8")
        actions = install(self.root, tools="auto")
        self.assertIn(("kept-user-edit", "claude:c4spec-propose"), actions)
        self.assertFalse(spot.is_symlink())
        self.assertEqual((spot / "SKILL.md").read_text(encoding="utf-8"), "# my own notes\n")
        install(self.root, tools="auto", force=True)
        self.assertTrue(spot.is_symlink())

    def test_no_link_support_falls_back_to_a_copy(self):
        with mock.patch("install.os.symlink", side_effect=OSError("no links here")):
            actions = install(self.root, tools="auto")
        self.assertIn(("copied-no-link-support", "claude:c4spec-propose"), actions)
        spot = self.root / ".claude" / "skills" / "c4spec-propose"
        self.assertFalse(spot.is_symlink())
        self.assertEqual((spot / "SKILL.md").read_bytes(), (self._shared() / "SKILL.md").read_bytes())
        # A copy equal to the shared one is not rewritten on every run.
        repeat = install(self.root, tools="auto")
        self.assertIn(("already-copied", "claude:c4spec-propose"), repeat)

    def test_no_link_fallback_ships_the_bundled_assets(self):
        """A fallback copy that drops scripts/schemas installs a broken skill."""
        with mock.patch("install.os.symlink", side_effect=OSError("no links here")):
            install(self.root, tools="claude")
        installed = self.root / ".claude" / "skills" / "c4spec"
        self.assertTrue((installed / "scripts" / "check.py").is_file(), "validator missing")
        self.assertTrue((installed / "scripts" / "diff.py").is_file())
        self.assertTrue((installed / "scripts" / "provenance.py").is_file())
        self.assertTrue((installed / "scripts" / "render_review.py").is_file())
        self.assertTrue((installed / "schemas" / "change.schema.json").is_file())
        self.assertTrue((installed / "references" / "c4-governance.md").is_file())
        self.assertTrue((installed / "requirements.txt").is_file())
        example = REPO / "examples/mini-project"
        result = subprocess.run(
            [sys.executable, str(installed / "scripts" / "check.py"),
             "--change", str(example / "c4spec/changes/add-cache.json"),
             "--constraints-file", str(example / "c4spec/constraints.json"),
             "--repo-root", str(example), "--phase", "proposal"],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_edited_asset_in_a_fallback_copy_is_kept(self):
        with mock.patch("install.os.symlink", side_effect=OSError("no links here")):
            install(self.root, tools="claude")
        asset = self.root / ".claude" / "skills" / "c4spec" / "scripts" / "diff.py"
        asset.write_text(asset.read_text(encoding="utf-8") + "\n# local patch\n", encoding="utf-8")
        actions = install(self.root, tools="claude")
        self.assertIn(("kept-user-edit", "claude:c4spec"), actions)
        self.assertIn("# local patch", asset.read_text(encoding="utf-8"))

    def test_default_install_wires_no_agent(self):
        """Per-agent wiring is the skills.sh CLI's job, not this script's."""
        actions = install(self.root)
        self.assertTrue(all(":" not in name for _, name in actions), actions)
        self.assertFalse((self.root / ".claude" / "skills").exists())
        self.assertFalse((self.root / ".hermes" / "skills").exists())

    def test_explicit_tool_selection_and_unknown_tool(self):
        install(self.root, tools="hermes")
        self.assertFalse((self.root / ".claude" / "skills").exists())
        self.assertTrue((self.root / ".hermes" / "skills" / "c4spec-propose").is_symlink())
        with self.assertRaises(InstallError):
            install(self.root, tools="kiro")

    def test_dry_run_creates_no_links(self):
        actions = install(self.root, tools="auto", dry_run=True)
        self.assertIn(("would-link", "claude:c4spec-propose"), actions)
        self.assertFalse((self.root / ".claude" / "skills").exists())


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.target = self.root / ".agents" / "skills" / "c4spec"
        self.target.mkdir(parents=True)
        (self.target / "SKILL.md").write_text("# skill\n", encoding="utf-8")
        self.spot = self.root / ".claude" / "skills" / "c4spec"

    def tearDown(self):
        self._temp.cleanup()

    def test_missing_empty_and_fallback_copy(self):
        self.assertEqual(classify_skill_spot(self.spot, self.target), "missing")
        self.spot.mkdir(parents=True)
        self.assertEqual(classify_skill_spot(self.spot, self.target), "missing", "empty folder")
        (self.spot / ".DS_Store").write_bytes(b"junk")
        self.assertEqual(classify_skill_spot(self.spot, self.target), "missing", "OS junk only")
        (self.spot / "SKILL.md").write_text("# skill\r\n", encoding="utf-8")
        self.assertEqual(classify_skill_spot(self.spot, self.target), "copy", "CRLF is not an edit")

    def test_extra_files_or_edits_belong_to_the_user(self):
        self.spot.mkdir(parents=True)
        (self.spot / "SKILL.md").write_text("# skill\n", encoding="utf-8")
        (self.spot / "notes.md").write_text("mine\n", encoding="utf-8")
        self.assertEqual(classify_skill_spot(self.spot, self.target), "user")
        (self.spot / "notes.md").unlink()
        (self.spot / "SKILL.md").write_text("# edited\n", encoding="utf-8")
        self.assertEqual(classify_skill_spot(self.spot, self.target), "user")

    def test_multifile_copy_is_recognised_and_caches_ignored(self):
        (self.target / "scripts").mkdir()
        (self.target / "scripts" / "check.py").write_text("# check\n", encoding="utf-8")
        shutil.copytree(self.target, self.spot)
        self.assertEqual(classify_skill_spot(self.spot, self.target), "copy")
        # Caches the validator leaves behind are not the user's edit.
        (self.spot / "scripts" / "__pycache__").mkdir()
        (self.spot / "scripts" / "__pycache__" / "check.cpython-312.pyc").write_bytes(b"x")
        (self.spot / ".DS_Store").write_bytes(b"junk")
        self.assertEqual(classify_skill_spot(self.spot, self.target), "copy")
        (self.spot / "scripts" / "check.py").write_text("# edited\n", encoding="utf-8")
        self.assertEqual(classify_skill_spot(self.spot, self.target), "user")

    def test_link_text_is_relative_to_the_link_folder(self):
        self.assertEqual(
            skill_link_text(self.spot, self.target),
            os.path.join("..", "..", ".agents", "skills", "c4spec"),
        )

    def test_create_skill_link_honours_an_unsupported_symlink(self):
        made = create_skill_link(self.spot, self.target,
                                 symlink=mock.Mock(side_effect=OSError("nope")))
        self.assertEqual(made, "copy")
        self.assertEqual((self.spot / "SKILL.md").read_text(encoding="utf-8"), "# skill\n")

    def test_failed_replacement_preserves_existing_skill(self):
        self.spot.mkdir(parents=True)
        installed = self.spot / "SKILL.md"
        installed.write_text("# my current skill\n", encoding="utf-8")
        with mock.patch("install.shutil.copytree", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                create_skill_link(self.spot, self.target,
                                  symlink=mock.Mock(side_effect=OSError("no links")))
        self.assertEqual(installed.read_text(encoding="utf-8"), "# my current skill\n")


if __name__ == "__main__":
    unittest.main()
