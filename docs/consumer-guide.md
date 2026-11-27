# Using C4Spec in an existing project

Keep the project's existing LikeC4 model, code, tests and directory layout.
Use a feature branch and pin the published compiler. The tested native pin is
**1.61.0**; compatibility checks still cover direct edits on **1.60.0**.

## Install

With Node.js 22.23.3, run this in a reviewed C4Spec checkout:

```bash
npm ci
npm run build
npm install -g .
cd /path/to/project
c4spec doctor
c4spec validate
```

Use `c4spec init --agent codex claude-code --dry-run` to preview the starter
model and the default `basic` profile. Omit `--dry-run` to install the shared
modeling and diagram maintenance skills. Choose `--profile extended` to
include the model-first workflow skills. Run the extended command later with
the same agents to add missing skills while preserving existing files.
Both profiles preserve an existing LikeC4 model. Run `c4spec init` without
`--agent` to set up only the model.

Use `--repo /path/to/project` to run from another directory. By default the CLI
recognizes `architecture/`, `docs/architecture/`, a root-level model, or a
single directory containing LikeC4 sources. Pass `--model-dir` for a custom or
ambiguous layout and `--project` to select a project in a multi-project export.

The shared skill bundles C4Spec-maintained DSL/CLI instructions in
`references/likec4/README.md`; install no separate upstream DSL skill. The
validated compiler is **exactly 1.61.0**, not an open-ended minimum. Follow the
bundled upgrade procedure before declaring another release compatible.

When upgrading an earlier installation, retire the redundant `likec4-dsl`
directory, agent links and lock entry in the reviewed Git change after checking
for local edits. The C4Spec bundle replaces that separate instruction source.

Check the installed files and `skills-lock.json`. With one agent, skills may
live directly in its own folder. The CLI also works independently of installed
skills. See [distribution](skill-distribution.md) for other agents and
skills-only installs.

## Maintain current-state diagrams on demand

Install the [basic profile](skill-distribution.md#choose-an-installation-profile)
with `c4spec init --agent codex`.
Then ask for a specific review or edit. For example, “Use `c4spec-maintain` to
check whether the checkout diagram shows the payment fallback we shipped.”
If the diagram needs a correction, ask the agent to make a focused edit.
For an update that is already implemented on your PR branch, diagram edits can
go in the same PR.

The skill uses the existing C4 model and checks the evidence at the revision
it documents. It validates model edits with the project's compiler pin and
previews the affected views. The result is a normal Git patch to the model or
views. OpenSpec or the existing development process continues to own proposals,
requirements and implementation.

Use [direct Git comparison](#direct-git-comparison-and-behavioral-obligations)
to inspect the committed change. The optional PR workflow below can show
rendered changes directly in GitHub.

## GitHub PR diagram review

An installed diagram workflow works with direct model edits and native
proposals. It compares the LikeC4 renders from the Git merge base and PR head
for the configured model directories. For a visible change, the workflow
uploads PNGs as the **c4spec-rendered-diagrams** artifact on the Actions run.
For pull requests from a branch in the same repository, it also posts or
updates one inline Mermaid comment. For supported
static views, one diagram shows green additions and dashed red removals.
A relationship label edit shows both labels between the same endpoints.
Layout and other visual changes that the overlay cannot represent use the
Before and After renders. The workflow clears the comment when the renders
match. On a fork pull request, open the **LikeC4 PR diagram changes** check
and download the artifact from the run summary once GitHub allows the workflow
to run. First-time contributors may need a maintainer to approve the run.
Review the raw model patch in **Files changed** as well.

Set it up per repository using the [reference workflow](../.github/workflows/pr-model-diff.yml)
and [renderer](../scripts/pr_model_diff.py) from the same reviewed C4Spec
revision. In the render job, run `npm ci --omit=dev` in that C4Spec checkout
to install the pinned compiler. Run its renderer from the consumer checkout
with full Git history. Pass the C4Spec checkout's `node_modules/.bin/likec4`
as `--compiler` and set `--model-dir` to each repository-relative LikeC4
project directory. The renderer loads its helpers and the 1.61.0 pin from
the C4Spec checkout.
Run the renderer on the `pull_request` event with read-only contents
permission and without persisted checkout credentials. Restrict the separate
comment publishing job to same-repository pull requests.
Skill installation and `c4spec init` leave workflow setup to the repository.

## Develop changes from the model

Install the extended profile with
`c4spec init --agent codex --profile extended`. Use the following sections
when C4Spec owns the model-first design workflow.

### Choose the correct proposal representation

| Change | Representation |
| --- | --- |
| Add/remove an architectural element or directed relationship | Native named `diff` on 1.61 |
| Add tags, links or metadata to an existing element | Native extension, validated before listing |
| Change an existing title, description or technology | Direct source edit on the branch, preserving identity |
| Add/change a view | Direct source edit; review selectors and computed view membership |
| Behavior/configuration without architecture impact | Existing code/tests/contracts; zero model delta |

Native 1.61 extensions do **not** accept arbitrary element properties. In a
consumer pilot, a `technology` edit exposed this behavior:
`diff list --json` exited 0 while validate/apply rejected the syntax. Always
validate first. Do not replace a logical node to manufacture a visual diff.

### Native proposal and review

Commit a supported named `diff` in the canonical model. Pin the exact Git
merge-base and proposal SHA. Then:

```bash
c4spec review --model-dir architecture --diff CHANGE_NAME \
  --base origin/main --out /tmp/c4spec-review-unique-name
```

The CLI resolves the merge base and records both commit IDs. The output
directory must be new, with an existing parent outside the repository. The CLI:

1. Verifies that all model sources/config match the committed proposal.
2. Validates with pinned 1.61.0, lists diffs and checks a nonmutating dry-run.
3. Builds the official native viewer and applies only a scratch copy.
4. Saves the source patch, native impact, advisory semantic delta and expected
   applied source manifest.

Open `review-site/index.html`, choose a focused view and the named diff, then
inspect **As-is / Changes / To-be**, `source.patch` and `semantic-diff.json`.
Serve the directory locally if the browser cannot open the standalone HTML.
The review copies committed regular files under the selected model directory.
Use a dedicated model directory if the model needs local assets. With a model
at the repository root, only LikeC4 sources and configuration are copied.
Assets outside the selected directory need the project's compiler workflow.

The thin helper supports **one pending native diff**. Isolate or reconcile other
proposals first. A native dry-run can exit 0 despite overlapping proposals; actual apply rejects
the overlap. The helper keeps one proposal per packet rather than guessing
independence or including another pending design in its expected applied result.

Obtain the necessary human design/implementation authorization. Existing
authorization for a bounded test remains valid; a bot comment is not approval.

### Authorized apply and verification

```bash
c4spec review --check-proposal /tmp/c4spec-review-unique-name/review.json
# Implement and test the authorized code/config change as applicable.
npm exec --yes --package=likec4@1.61.0 -- likec4 diff apply CHANGE_NAME --dry-run architecture
npm exec --yes --package=likec4@1.61.0 -- likec4 diff apply CHANGE_NAME architecture
git diff -- architecture
# Inspect and commit ALL compiler-edited files; apply can use another owning file.
c4spec review --check-applied /tmp/c4spec-review-unique-name/review.json
```

The last check requires a committed descendant whose model bytes exactly match
the reviewed scratch result. Source or proposal-SHA drift requires renewed
review; overlapping diffs are not bypassed. Run the project's real tests and
model/evidence checks separately. The packet never claims tests executed,
runtime conformance or authenticated human approval. Use the same tool to
produce and verify a packet. The legacy Python helper has its own format.

## Direct Git comparison and behavioral obligations

Validate the working model, then compare the committed model:

```bash
c4spec validate
c4spec diff --base origin/main --json
c4spec diff --base origin/main --source
```

For an HTML review bundle with both commit viewers, run
`c4spec review --base origin/main --out /tmp/c4spec-direct-review`.
For committed model directory moves, use `c4spec diff --base origin/main --model-dir .`
to compare both paths.
Inspect the raw patch too because computed exports can omit some source
selectors. A new view with zero element or relationship changes is still a
real view change. For consumers pinned to 1.60.0, use the version-matched
[legacy compatibility commands](../README.md#legacy-scripts-and-teaching-fixtures).

No change JSON is required for model-only checks. If the project has a compact
record for obligations absent from tests/contracts, pass `--change <path>` and
check both `--phase proposal` and `--phase completion`; add an existing durable
register with `--constraints-file <path>`. Planned/absent evidence must keep
completion failing. File existence does not establish passing tests.

Use the Git commit IDs and raw source patch to identify what was reviewed.
The CLI reports structural verification independently from consumer tests.
Validation failures use exit status 1 and invalid command input uses status 2.

## Finish

Prepare one normal PR with model/code changes, actual commands/results,
focused visuals and unresolved decisions. Keep generated JSON/HTML/PNG/Markdown
out of Git. Retain lasting rationale in PR/Git history because native apply
removes the diff description. Human merge advances the canonical state.
