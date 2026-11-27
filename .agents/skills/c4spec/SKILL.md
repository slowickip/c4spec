---
name: c4spec
description: Shared C4Spec guidance for modeling, validating and reviewing C4 architecture in LikeC4 and Git.
license: Apache-2.0
---

# C4Spec shared contract

When developing C4Spec itself, read the source repository README and follow its
contributor instructions. In a maintainer checkout that includes
`docs/PROJECT_PLAN.md`, `docs/STATUS.md`, and `docs/decisions.md`, read them for
the owner’s agreements and current handoff.

Read `references/c4-governance.md` beside this skill and inspect the consuming
project's `AGENTS.md`, instructions and existing architecture.

**LikeC4 owns architectural structure**. Use only its native `.c4` model
as an authored architecture source. Views are projections, not independent
model definitions. Keep stable element and view IDs where identity survives,
and keep existing project specifications in their own workflow.

## Maintain and review the model

On an explicit request to inspect or update current-state diagrams, use
`c4spec-maintain`. Review against repository evidence and make focused Git
edits when requested. The project's delivery process owns its specifications
and implementation. Use `c4spec validate` for model checks and `c4spec diff`
for committed edits. Preview the affected views in LikeC4 and inspect the Git
patch, including selectors the computed comparison may omit. Configured
GitHub PR diagram review shows visible render changes.

## LikeC4 compatibility and bundled guidance

**Validated LikeC4 version: 1.61.0.** Newer releases are unverified until
C4Spec runs compatibility checks and updates its owned skills/scripts for the
candidate feature set. Do not infer compatibility from a version range or
silently upgrade a consumer. The existing 1.60.0 fixtures cover legacy direct
edits only; native diffs require the validated 1.61.0 path.

Read [the bundled LikeC4 guide](references/likec4/README.md) before authoring
models or running the CLI, then load its relevant topic references. C4Spec
maintains this DSL/CLI guidance and its upgrade procedure as part of this
shared skill. No separate upstream skill installation or live prompt is needed.

## Model checks

Run the project's pinned LikeC4 compiler. Use `c4spec validate` when the CLI
matches the pin. For a skills-only install, use the project's LikeC4 CLI.
Optional computed-model checks, schemas and helpers are bundled under
`scripts/` and `schemas/` beside this skill. Compilation validates model
syntax and references. Source evidence and executed tests establish separate
facts about the implementation.

## Provenance

The bundled LikeC4 guidance includes its source revision and MIT license in
`references/likec4/`. See `docs/upstream-reuse.md` in the tool repository for
the distribution's third-party source and license records.
