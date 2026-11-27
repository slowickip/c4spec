#!/usr/bin/env python3
"""Source-bound provenance for one LikeC4 model directory and one export file.

Records a deterministic manifest of every ``.c4``/``.likec4`` source and LikeC4
project config (sorted relative paths plus SHA-256), the exact Git commit those
bytes are verified against, the LikeC4 compiler version actually invoked, and
the SHA-256 of the exported JSON bytes.

Standard library only; the ``git`` CLI is used for verification. Coverage is
deliberately narrow: external imports, sources outside the given model
directory and LikeC4 semantics the export omits are NOT covered. A generated
export that is tracked by Git is rejected, never described.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import subprocess

SCHEMA_VERSION = 1
KIND = "c4spec-provenance"
SOURCE_SUFFIXES = (".c4", ".likec4")
CONFIG_NAMES = frozenset({
    "likec4.config.json",
    "likec4.config.js",
    "likec4.config.ts",
    "likec4.config.mjs",
    "likec4.config.cjs",
    ".likec4rc",
})
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

PROVENANCE_KEYS = frozenset({
    "schemaVersion", "kind", "modelDir", "gitCommit", "gitVerified",
    "compilerVersion", "compilerCommandReported", "sources", "sourcesDigest",
    "export", "limitations",
})
PROVENANCE_REQUIRED = PROVENANCE_KEYS - {"kind"}
EXPORT_KEYS = frozenset({"sha256", "projectId", "projectIds", "insideWorkTree"})

LIMITATIONS = [
    "Only .c4/.likec4 files and the LikeC4 project config inside the given model directory are covered; external imports or a config outside that directory are not.",
    "Git verification compares working-tree bytes with the named commit and enumerates that commit's sources, so uncommitted edits and omitted files are rejected rather than silently described.",
    "The compiler version is producer-reported: --compiler-version is a claim, and --compiler-command only proves some command printed that string. The export is not bound to the compiler that generated it, so the exporter stays unverified.",
    "The manifest covers source bytes, not LikeC4 semantics; a review fingerprint must bind both.",
    "Generated exports must never be committed; an export tracked by Git is rejected.",
]


class InputError(ValueError):
    """Invalid or unverifiable provenance input."""


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def manifest_digest(sources):
    """Digest of the manifest itself, so a reordered or edited list is visible."""
    return "sha256:" + sha256_bytes(canon(sources).encode("utf-8"))


def is_source_name(name):
    return name.endswith(SOURCE_SUFFIXES) or name in CONFIG_NAMES or name.startswith(".likec4rc")


def is_config_name(name):
    return name in CONFIG_NAMES or name.startswith(".likec4rc")


def collect_sources(model_dir):
    """Every .c4/.likec4 source and project config under ``model_dir``, sorted."""
    root = Path(model_dir)
    if root.is_symlink():
        raise InputError("model directory must not be a symlink")
    root = root.resolve()
    if not root.is_dir():
        raise InputError("model directory must exist and be a directory")
    found = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames:
            if (Path(dirpath) / name).is_symlink():
                raise InputError("symlinked directory is not supported: " + name)
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                raise InputError("symlinked source is not supported: " + full.relative_to(root).as_posix())
            if not is_source_name(name):
                continue
            rel = full.relative_to(root).as_posix()
            key = rel.casefold()
            if key in found:
                raise InputError("duplicate source path (case-insensitive): " + rel)
            resolved = full.resolve()
            if not resolved.is_relative_to(root):
                raise InputError("source escapes the model directory: " + rel)
            if not resolved.is_file():
                raise InputError("source is not a regular file: " + rel)
            found[key] = {"path": rel, "sha256": sha256_file(resolved)}
    sources = sorted(found.values(), key=lambda entry: entry["path"])
    if not sources:
        raise InputError("no .c4/.likec4 sources found in the model directory")
    configs = [entry["path"] for entry in sources if is_config_name(posixpath.basename(entry["path"]))]
    if not configs:
        raise InputError("no LikeC4 project config found in the model directory")
    if len(configs) > 1:
        raise InputError("multiple LikeC4 project configs found; point at exactly one project")
    return sources


def _git(cwd, *args):
    try:
        completed = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True)
    except OSError as ex:  # git not installed
        raise InputError("git is required to verify provenance") from ex
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise InputError("git " + " ".join(args) + " failed: " + detail)
    return completed.stdout


def git_toplevel(path):
    if not Path(path).is_dir():
        raise InputError("repository root must be an existing directory")
    return Path(_git(path, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()


def verify_sources_at_commit(toplevel, model_rel, sources, commit):
    """Prove the manifest is complete for ``commit`` and that every byte matches."""
    toplevel = Path(toplevel).resolve()
    if not HEX40.match(commit or ""):
        raise InputError("git commit must be a full 40-character lowercase SHA")
    _git(toplevel, "cat-file", "-e", commit + "^{commit}")
    listed = _git(toplevel, "ls-tree", "-r", "--name-only", commit, "--", model_rel or ".").decode("utf-8")
    committed = set()
    for line in listed.splitlines():
        path = line.strip()
        if not path:
            continue
        if model_rel:
            if not path.startswith(model_rel + "/"):
                continue
            path = path[len(model_rel) + 1:]
        if is_source_name(posixpath.basename(path)):
            committed.add(path)
    manifest = {entry["path"] for entry in sources}
    omitted = sorted(committed - manifest)
    if omitted:
        raise InputError("manifest omits sources committed at " + commit + ": " + ", ".join(omitted))
    foreign = sorted(manifest - committed)
    if foreign:
        raise InputError("manifest lists sources absent from commit " + commit + ": " + ", ".join(foreign))
    for entry in sources:
        repo_path = posixpath.join(model_rel, entry["path"]) if model_rel else entry["path"]
        blob = _git(toplevel, "cat-file", "blob", commit + ":" + repo_path)
        if sha256_bytes(blob) != entry["sha256"]:
            raise InputError(
                "working source does not match commit " + commit + ": " + entry["path"]
                + " (uncommitted edit, stale worktree, or wrong commit)")


def verify_git_sources(model_dir, sources, commit):
    """Verify the manifest against ``commit`` and return the repo-relative dir."""
    toplevel = git_toplevel(model_dir)
    prefix = _git(Path(model_dir).resolve(), "rev-parse", "--show-prefix").decode("utf-8").strip()
    model_rel = prefix.rstrip("/")
    verify_sources_at_commit(toplevel, model_rel, sources, commit)
    return model_rel


def inspect_export(path, project=None, toplevel=None):
    export = Path(path)
    if export.is_symlink():
        raise InputError("export must not be a symlink")
    if not export.is_file():
        raise InputError("export must be an existing regular file")
    raw = export.read_bytes()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as ex:
        raise InputError("export is not valid UTF-8 JSON") from ex
    entries = parsed if isinstance(parsed, list) else [parsed]
    ids = sorted({entry["projectId"] for entry in entries
                  if isinstance(entry, dict) and isinstance(entry.get("projectId"), str)})
    if not ids:
        raise InputError("export does not contain a LikeC4 projectId")
    if project is not None and project not in ids:
        raise InputError("requested project is not present in the export: " + project)
    if project is None and len(ids) > 1:
        raise InputError("export contains multiple project IDs; pass --project explicitly")
    inside = False
    if toplevel is not None:
        resolved = export.resolve()
        inside = resolved.is_relative_to(Path(toplevel).resolve())
        if inside:
            rel = resolved.relative_to(Path(toplevel).resolve()).as_posix()
            tracked = subprocess.run(["git", "-C", str(toplevel), "ls-files", "--error-unmatch", "--", rel],
                                     capture_output=True)
            if tracked.returncode == 0:
                raise InputError("export is tracked by Git; generated exports must not be committed: " + rel)
    return {"sha256": sha256_bytes(raw), "projectId": project or ids[0],
            "projectIds": ids, "insideWorkTree": inside}


def compiler_command_reported(compiler_version, compiler_command):
    """True when a producer-run command printed the version; it never binds the export."""
    if not compiler_command:
        return False
    try:
        tokens = shlex.split(compiler_command)
    except ValueError as ex:
        raise InputError("compiler command cannot be parsed") from ex
    if not tokens:
        raise InputError("compiler command must not be empty")
    try:
        completed = subprocess.run(tokens, capture_output=True, text=True)
    except OSError as ex:
        raise InputError("compiler command could not be executed") from ex
    reported = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise InputError("compiler command failed: " + reported.strip()[:200])
    if compiler_version not in reported:
        raise InputError("compiler command does not report " + compiler_version + ": " + reported.strip()[:200])
    return True


def build_provenance(model_dir, export, commit, compiler_version, project=None, compiler_command=None):
    if not HEX40.match(commit or ""):
        raise InputError("git commit must be a full 40-character lowercase SHA")
    if not VERSION.match(compiler_version or ""):
        raise InputError("compiler version must be explicit, e.g. 1.60.0")
    sources = collect_sources(model_dir)
    model_rel = verify_git_sources(model_dir, sources, commit)
    reported = compiler_command_reported(compiler_version, compiler_command)
    document = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": KIND,
        "modelDir": model_rel,
        "gitCommit": commit,
        "gitVerified": True,
        "compilerVersion": compiler_version,
        "compilerCommandReported": reported,
        "sources": sources,
        "sourcesDigest": manifest_digest(sources),
        "export": inspect_export(export, project, git_toplevel(model_dir)),
        "limitations": list(LIMITATIONS),
    }
    return document


def _valid_source_path(raw):
    if not isinstance(raw, str) or not raw or "\\" in raw or raw.startswith(("/", "~")):
        return False
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return is_source_name(parts[-1])


def validate_provenance(document, label="provenance"):
    """Fail closed on a malformed, reordered or internally inconsistent artifact."""
    if not isinstance(document, dict):
        raise InputError(label + " must be a JSON object")
    unknown = set(document) - PROVENANCE_KEYS
    if unknown:
        raise InputError(label + " has unknown fields: " + ", ".join(sorted(unknown)))
    missing = PROVENANCE_REQUIRED - set(document)
    if missing:
        raise InputError(label + " is missing fields: " + ", ".join(sorted(missing)))
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != SCHEMA_VERSION:
        raise InputError(label + " has an unsupported schemaVersion")
    if document.get("kind") != KIND:
        raise InputError(label + " is not a " + KIND + " artifact")
    model_dir = document["modelDir"]
    if not isinstance(model_dir, str) or model_dir.startswith(("/", "~")) or "\\" in model_dir:
        raise InputError(label + " modelDir must be a repository-relative path")
    if any(part in {"", ".", ".."} for part in model_dir.split("/")) and model_dir != "":
        raise InputError(label + " modelDir must be normalized")
    if not HEX40.match(str(document["gitCommit"])):
        raise InputError(label + " gitCommit must be a full 40-character lowercase SHA")
    if document["gitVerified"] is not True:
        raise InputError(label + " was not verified against its Git commit")
    if not VERSION.match(str(document["compilerVersion"])):
        raise InputError(label + " compilerVersion must be explicit, e.g. 1.60.0")
    if not isinstance(document["compilerCommandReported"], bool):
        raise InputError(label + " compilerCommandReported must be a boolean")
    sources = document["sources"]
    if not isinstance(sources, list) or not sources:
        raise InputError(label + " sources must be a non-empty list")
    seen = set()
    previous = None
    for index, entry in enumerate(sources):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise InputError(f"{label} sources.{index} must contain only path and sha256")
        path, digest = entry["path"], entry["sha256"]
        if not _valid_source_path(path):
            raise InputError(f"{label} sources.{index} is not a safe .c4/config path: {path!r}")
        if not HEX64.match(str(digest)):
            raise InputError(f"{label} sources.{index} sha256 must be 64 lowercase hex characters")
        if path in seen or path.casefold() in {value.casefold() for value in seen}:
            raise InputError(f"{label} sources contains a duplicate path: {path}")
        seen.add(path)
        if previous is not None and path <= previous:
            raise InputError(label + " sources must be sorted by path without duplicates")
        previous = path
    if document["sourcesDigest"] != manifest_digest(sources):
        raise InputError(label + " sourcesDigest does not match its own source manifest")
    export = document["export"]
    if not isinstance(export, dict) or set(export) != EXPORT_KEYS:
        raise InputError(label + " export must contain only sha256, projectId, projectIds and insideWorkTree")
    if not HEX64.match(str(export["sha256"])):
        raise InputError(label + " export sha256 must be 64 lowercase hex characters")
    ids = export["projectIds"]
    if not isinstance(ids, list) or not ids or any(not isinstance(value, str) or not value for value in ids):
        raise InputError(label + " export projectIds must be a non-empty list of strings")
    if len(ids) != len(set(ids)) or ids != sorted(ids):
        raise InputError(label + " export projectIds must be sorted and unique")
    if export["projectId"] not in ids:
        raise InputError(label + " export projectId must belong to projectIds")
    if not isinstance(export["insideWorkTree"], bool):
        raise InputError(label + " export insideWorkTree must be a boolean")
    limitations = document["limitations"]
    if not isinstance(limitations, list) or any(not isinstance(value, str) for value in limitations):
        raise InputError(label + " limitations must be a list of strings")
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, help="LikeC4 project directory containing its config")
    parser.add_argument("--export", required=True, help="Existing exported LikeC4 JSON (absolute path recommended)")
    parser.add_argument("--git-commit", required=True, help="Full 40-character commit SHA the sources belong to")
    parser.add_argument("--compiler-version", required=True, help="LikeC4 version actually invoked for the export")
    parser.add_argument("--compiler-command",
                        help="Producer-run command whose output must contain --compiler-version; command-output match only, never export binding")
    parser.add_argument("--project", help="Exact LikeC4 projectId when the export holds more than one")
    parser.add_argument("--out", help="Write the provenance JSON here instead of stdout")
    args = parser.parse_args(argv)
    try:
        document = build_provenance(args.model_dir, args.export, args.git_commit,
                                    args.compiler_version, args.project, args.compiler_command)
    except (OSError, InputError) as ex:
        parser.exit(2, "Cannot build provenance: " + str(ex) + "\n")
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
