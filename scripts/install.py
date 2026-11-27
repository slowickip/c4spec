#!/usr/bin/env python3
"""Copy C4Spec skills from this checkout into a project without network access."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / ".agents" / "skills"
SHARED_SKILLS = Path(".agents") / "skills"


class InstallError(ValueError):
    """A target or an option that cannot be installed as asked."""


OFFLINE_AGENTS = ("claude", "cursor", "hermes", "continue")
HERMES_MARKERS = ("HERMES.md", ".hermes.md")

# Keep cache and filesystem metadata out of skill copies and comparisons.
IGNORED_NAMES = (".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__", "metadata.json")
IGNORED_SUFFIXES = (".pyc", ".pyo")


def _is_ignored(name: str) -> bool:
    return (
        name in IGNORED_NAMES
        or name.startswith("._")
        or name.endswith(IGNORED_SUFFIXES)
    )


def _ignore_junk(directory, names):
    """Filter out cache and filesystem metadata while copying a skill."""
    return [name for name in names if _is_ignored(name)]


def _file_digest(path: Path) -> str:
    data = path.read_bytes()
    try:
        text = _normalize(data.decode("utf-8"))
    except UnicodeDecodeError:
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _skill_manifest(directory: Path):
    """Every meaningful file under `directory`: (relative path, digest).

    Line endings are normalised, so a CRLF checkout of an untouched skill is
    still recognised as an unedited copy rather than as the user's edit. The
    digest alone is compared — a byte count would flag that CRLF difference.
    """
    manifest = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(name for name in dirs if not _is_ignored(name))
        for name in sorted(files):
            if _is_ignored(name):
                continue
            path = Path(root) / name
            manifest.append((path.relative_to(directory).as_posix(), _file_digest(path)))
    return tuple(manifest)


def _normalize(content: str) -> str:
    """Drop what a checkout adds without anyone editing the file."""
    return content.lstrip("\ufeff").replace("\r\n", "\n")


def skill_link_text(link_path: Path, target_dir: Path) -> str:
    """Locate the shared skill relative to the directory containing its link."""
    project = target_dir.parent.parent.parent
    # Resolve the project while preserving the path through its shared folder.
    source = project.resolve() / target_dir.relative_to(project)
    return os.path.relpath(source, start=link_path.parent.resolve())


def classify_skill_spot(link_path: Path, target_dir: Path) -> str:
    """Identify a free path, our link or copy, or a path owned by the project."""
    try:
        if link_path.is_symlink():
            return "link" if link_path.resolve() == target_dir.resolve() else "user"

        entries = {entry.name: entry for entry in link_path.iterdir()
                   if not _is_ignored(entry.name)}
        if not entries:
            return "missing"

        definition = entries.get("SKILL.md")
        if definition is not None and not definition.is_symlink() and definition.is_file():
            if _skill_manifest(link_path) == _skill_manifest(target_dir):
                return "copy"
    except FileNotFoundError:
        # A file can disappear during the comparison. Only an absent slot is free.
        return "missing" if not link_path.exists() and not link_path.is_symlink() else "user"
    except (OSError, RuntimeError):
        return "user"
    return "user"


def create_skill_link(link_path: Path, target_dir: Path, symlink=None) -> str:
    """Prepare the replacement before moving the existing installation."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    make_link = os.symlink if symlink is None else symlink
    with TemporaryDirectory(prefix=".c4spec-", dir=link_path.parent) as staging:
        incoming = Path(staging) / "skill"
        try:
            make_link(skill_link_text(link_path, target_dir), str(incoming), True)
            result = "link"
        except (OSError, NotImplementedError):
            shutil.copytree(target_dir, incoming, ignore=_ignore_junk)
            result = "copy"

        previous = Path(staging) / "previous"
        if link_path.is_symlink() or link_path.exists():
            link_path.rename(previous)
        try:
            incoming.rename(link_path)
        except OSError:
            if previous.is_symlink() or previous.exists():
                previous.rename(link_path)
            raise
    return result


def _shared_copy(skill: Path, destination: Path, *, dry_run: bool, force: bool) -> str:
    """Copy one skill into the shared folder, or report why it was left alone."""
    path = destination / skill.name
    if (path.exists() or path.is_symlink()) and not force:
        return "skipped-existing"
    if dry_run:
        return "would-install"
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill, path, symlinks=False, ignore=_ignore_junk)
    return "installed"


def select_tools(root: Path, requested: str) -> list[str]:
    """Select the agent directories to populate for an offline installation."""
    if requested == "all":
        return list(OFFLINE_AGENTS)
    if requested == "none":
        return []

    if requested == "auto":
        detected = {agent for agent in OFFLINE_AGENTS if (root / f".{agent}").exists()}
        if any((root / marker).exists() for marker in HERMES_MARKERS):
            detected.add("hermes")
        return [agent for agent in OFFLINE_AGENTS if agent in detected]

    names = {name.strip() for name in requested.split(",") if name.strip()}
    known = set(OFFLINE_AGENTS) | {"codex"}
    if unknown := names - known:
        raise InstallError(
            f"Unsupported tool(s): {', '.join(sorted(unknown))}. Supported: "
            f"{', '.join(sorted(known))}"
        )
    return [agent for agent in OFFLINE_AGENTS if agent in names]


def install(target, *, dry_run=False, force=False, tools="none"):
    """Install the shared skills, plus per-tool links only when asked.

    `tools` defaults to `none`: per-agent wiring belongs to the standard
    skills.sh CLI (`npx skills add`), which knows every agent and writes its own
    lock file. `auto`/`all`/ids are the offline fallback for a machine without
    Node, and cover only the agent conventions listed in `OFFLINE_AGENTS`.
    """
    root = Path(target).expanduser().resolve()
    if not root.is_dir():
        raise InstallError("Target repository directory does not exist")
    destination = root / SHARED_SKILLS
    actions = []
    installed = []
    for skill in sorted(SOURCE.glob("c4spec*")):
        if not skill.is_dir():
            continue
        status = _shared_copy(skill, destination, dry_run=dry_run, force=force)
        actions.append((status, skill.name))
        installed.append(skill.name)
    if not installed:
        raise InstallError("No C4Spec skills found to install")

    selected = select_tools(root, tools)
    for tool in selected:
        link_dir = root / f".{tool}" / "skills"
        for name in installed:
            spot = classify_skill_spot(link_dir / name, destination / name)
            if spot == "user" and not force:
                actions.append(("kept-user-edit", f"{tool}:{name}"))
                continue
            if spot == "link":
                actions.append(("already-linked", f"{tool}:{name}"))
                continue
            if spot == "copy" and not force:
                # A fallback copy equal to the shared copy stays: rewriting it
                # every run would churn the project for no change.
                actions.append(("already-copied", f"{tool}:{name}"))
                continue
            if dry_run:
                actions.append(("would-link", f"{tool}:{name}"))
                continue
            made = create_skill_link(link_dir / name, destination / name)
            status = "linked" if made == "link" else "copied-no-link-support"
            actions.append((status, f"{tool}:{name}"))
    return actions


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--tools",
        default="none",
        help="Offline fallback for per-agent wiring: 'auto' (detect), 'all', "
             "'none' (default — use the skills.sh CLI), or a comma-separated "
             f"list ({', '.join(OFFLINE_AGENTS)})",
    )
    a = p.parse_args(argv)
    try:
        rows = install(a.target, dry_run=a.dry_run, force=a.force, tools=a.tools)
        for status, name in rows:
            print(f"{status}: {name}")
        if a.tools == "none":
            print("hint: per-agent wiring is the skills.sh CLI's job — "
                  "npx skills add <repo-or-path> --skill '*' -a <agent> -y "
                  "(offline fallback here: --tools auto)")
        return 0
    except (OSError, InstallError) as ex:
        p.exit(2, f"Install failed: {ex}\n")


if __name__ == "__main__":
    raise SystemExit(main())
