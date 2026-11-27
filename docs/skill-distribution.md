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

The shared skill includes the [LikeC4 guidance](../.agents/skills/c4spec/references/likec4/README.md)
for the pinned compiler. The installer records a content hash in `skills-lock.json`.

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

## Install skills offline

From a source checkout, run `python3 scripts/install.py --target <repo>` to
copy the skills to `<repo>/.agents/skills/`. The Python installer needs no
network connection. Use `--dry-run` to preview the changes.

For agent-specific locations, pass `--tools auto` or choose from `claude`,
`cursor`, `hermes` and `continue`. The installer creates relative links
where supported and copies the skill directory elsewhere. It preserves
local edits by default. Review the differences before using `--force`.

## Installed files

| Agent selection with skills.sh | Shared skill location |
| --- | --- |
| `-a claude-code -a codex` | `.agents/skills/c4spec/`, linked from `.claude/skills/c4spec` |
| `-a claude-code` | `.claude/skills/c4spec/` |

Each installed skill includes its references and other bundled files. The
shared `c4spec` skill also contains the Python checks and schemas.

## Checks

```bash
python3 -m unittest discover -s tests -v     # classification, links, fallback, kept edits
npx --yes skills@1.8.1 add /path/to/c4spec --skill '*' -a claude-code -y --list   # what the CLI sees
```
