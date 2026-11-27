# How C4Spec skills reach an agent

The `c4spec init --agent codex claude-code` command uses the packaged
skills CLI with C4Spec's bundled skills. This note covers direct use of that
installer and the offline compatibility path.

## Choose an installation profile

Run the C4Spec CLI from the consuming project:

| Profile | Command | Skills |
| --- | --- | --- |
| Basic (default) | `c4spec init --agent codex` | `c4spec` and `c4spec-maintain` for diagram work on request |
| Extended | `c4spec init --agent codex --profile extended` | Basic skills plus the propose, review, apply, verify, finish, explore and continue skills |

Use `--agent codex claude-code` for both agents. Append `--dry-run` to see
which skills the CLI would add. You can opt into extended later with the same
agent selection. Both profiles add missing skills and preserve existing skill
files, including local edits. Review any incomplete skill directories or
agent links flagged by `init` before retrying.

## Install directly with skills.sh

From the consuming project, point the pinned skills CLI at a reviewed checkout:

```bash
npx --yes skills@1.8.1 add /path/to/c4spec --skill '*' -a claude-code -a codex -y
```

`-y` makes the install noninteractive, `-a` selects agents, and `--skill '*'`
installs all C4Spec skills. For a remote source, use `OWNER/REPO@COMMIT` with
the reviewed commit. Verify the installed files and `skills-lock.json`.

**Owned LikeC4 guidance:** the shared `c4spec` skill includes
`references/likec4/README.md`, topic references, runnable examples and the MIT
source notice. It is the only C4Spec DSL/CLI instruction bundle; no separate
`likec4-dsl` install is required. C4Spec declares exactly **1.61.0** compatible.
Refresh the compiler and owned guidance only after the documented compatibility
checks pass or the skills/scripts are adjusted to the candidate feature set.

Two consequences worth remembering: a remote install reads the *default branch*
(or a commit), not an arbitrary feature branch; and the lock file records a
content hash, which is the standard way to notice that installed skills drifted.

## Install only diagram maintenance

From the consumer repository, select the shared guidance and the maintenance
skill from the same reviewed checkout:

```bash
npx --yes skills@1.8.1 add /path/to/c4spec --skill c4spec c4spec-maintain -a codex -y
```

Select your agent with `-a`. These are the two skills in the CLI's basic
profile. The offline script installs the full bundle.

## Preview a skill upgrade

Run a C4Spec CLI built from the reviewed revision you want to adopt. In the
consumer checkout, use `c4spec doctor` to see the installed skill commits, CLI
version and validated LikeC4 version. Then run `c4spec update --dry-run` or
add `--json` for the per-file plan.

The preview compares the installed Codex and Claude Code skill files with
the running CLI's bundle. It reads version 2 `skills-lock.json` hashes to
flag changes at the skill-folder level. The file list shows differences
against the target bundle, which may also include upstream changes. Review
any entries reported as modified, unverified, missing or blocked before
upgrading. The command exits 1 if it cannot verify the installation or
finds drift. It uses local files and leaves the checkout and lock file intact.

## What `scripts/install.py` still adds

From a source checkout or source archive, `scripts/install.py` covers two cases
the Node CLI does not (npm tarball users already have Node and use `c4spec init`):

1. **Offline, pinned, private copy.** `python3 scripts/install.py --target <repo>`
   copies this repository's own skill text into `<repo>/.agents/skills/`. No
   Node, no network, no git auth, no lock file: the content is exactly the
   checkout you ran it from. Use it in CI setup, air-gapped machines, or a
   private fork where you do not want a second remote.
2. **A small offline link fallback.** `--tools auto|all|claude,hermes,…` links
   the shared copy into the agent folders of four conventions (`claude`,
   `cursor`, `hermes`, `continue`), relative and clone-safe, with a plain-copy
   fallback where the filesystem has no symlinks. It never overwrites a skill
   folder that holds an edit or extra files (`kept-user-edit`), and `--force`
   replaces it after review.

Default is `--tools none`, so a plain run does not guess which agents you use; it
prints the `npx skills add` line instead.

## Bundled assets survive distribution

`c4spec` is a multi-file skill: `SKILL.md` plus `scripts/check.py`,
`scripts/diff.py`, `schemas/*.json`, `references/` and `requirements.txt`.
Verified on 2026-11-12 with `skills` 1.8.1 against a fresh checkout — the
default distribution copies the **whole** folder in both shapes:

| Invocation | Result |
| --- | --- |
| `-a claude-code -a codex` | full copy in `.agents/skills/c4spec/…`, plus a relative symlink `.claude/skills/c4spec` → `../../.agents/skills/c4spec`; the validator runs through the link |
| `-a claude-code` only | full copy in `.claude/skills/c4spec/…`, no shared store |

The installed validator was executed from the agent folder against
`examples/mini-project` and returned `valid: true` (`jsonschema` from
`requirements.txt` installed). `scripts/install.py`'s offline fallback (no
symlink support) now copies the same tree; before that fix it copied only
`SKILL.md` and installed a skill whose validator could not run.

## Limitations

- A skill whose text changed keeps the old installed copy classified as a user
  edit; delete it or re-run with `--force`.
- The fallback links cover four agent conventions. Use the standard skills
  CLI for other agents.
- A private remote install depends on your Git credentials. Local installs
  use the checkout you pass to the CLI.

## Checks

```bash
python3 -m unittest discover -s tests -v     # classification, links, fallback, kept edits
npx --yes skills@1.8.1 add /path/to/c4spec --skill '*' -a claude-code -y --list   # what the CLI sees
```
