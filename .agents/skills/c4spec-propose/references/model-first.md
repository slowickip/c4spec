# Model-first development with C4Spec

Use this reference when the project opts into the C4Spec development
workflow. Read the shared `c4spec` skill for C4 governance and the validated
LikeC4 pin. The Python commands below run from the installed shared
`c4spec` skill directory, which also contains the schemas and references.

## Model-first proposals

**Native LikeC4 model diffs are the preferred architecture-change format**
when the consuming repository pins the validated release **1.61.0**.
On a feature branch, write a named `diff NAME { remove { ... } add { ... } }`
*within the existing canonical .c4/.likec4 sources*. The ordinary `model`
remains As-is; LikeC4 visualizes **As-is / Changes / To-be**, then
`likec4 diff apply NAME` writes the resulting canonical graph and deletes
the temporary diff. Never model the old and proposed nodes as two *current*
nodes just to simulate colors. Keep stable element identity when merely
modifying one logical element. Native 1.61 cannot change its title, description or technology through an extension; use direct Git edits and source/computed review for those properties and for views, even on 1.61.

**No per-change JSON file is required for architecture-only native diffs.**
Use the Git branch/PR for review intent, rationale and approval. Existing
tests/contracts are authoritative for detailed behavior; optional compact
change JSON may still capture important non-topological obligations that
cannot be represented in existing contracts/tests or a concise PR discussion.
Read the consuming project's `AGENTS.md` and follow its established
layout rather than forcing a new `c4spec/changes/` tree. Keep durable non-topological constraints in its
existing register (default `c4spec/constraints.json`) only when not already
covered by authoritative tests/contracts. If a JSON record is used, pass its
explicit path to `c4spec validate --change` (or `check.py --change` on the
legacy path); supply `--constraints-file` only
when checking an existing durable constraint register. Otherwise do not
invent a record or configuration file.

## Development skills

- `c4spec-explore` — investigate and compare alternatives (no mutation).
- `c4spec-continue` — inspect persisted change and Git state, recommend the next operation.
- `c4spec-propose` — prepare the model change for design review, using a native named `diff` for supported changes on 1.61.0.
- `c4spec-review` — inspect native **As-is / Changes / To-be**, raw source, overlaps and verification gaps; request human design review.
- `c4spec-apply` — implement only after explicit authorization, then preview and apply the approved native diff to the canonical model on the branch.
- `c4spec-verify` — actually run checks and surface possible drift.
- `c4spec-finish` — prepare PR; Git merge advances the canonical model.

A later skill may return to an earlier one. Use the `c4spec` CLI for
diagnostics, validation, committed Git diffs and review artifacts. The
existing LikeC4 preview in VS Code or the browser is the visual interface.

## Native model-diff flow (LikeC4 1.61.0)

```bash
npx --yes likec4@1.61.0 validate
npx --yes likec4@1.61.0 diff list --json
npx --yes likec4@1.61.0 diff apply CHANGE_NAME --dry-run
# Only after explicit human permission to apply the reviewed change:
npx --yes likec4@1.61.0 diff apply CHANGE_NAME
npx --yes likec4@1.61.0 validate
```

Review `likec4 start`'s As-is, Changes and To-be modes *before* applying,
plus the raw Git patch and the exact proposed commit. A dry-run must leave
source bytes unchanged. Overlaps **must not** be resolved automatically with
`--accept-overlaps`; get explicit agreement from affected change owners.
Applying a native diff removes its own description/comments, so preserve
lasting rationale in the Git PR/commit or an ADR if material. Re-review drift
between approved proposal and applied source. The feature branch may contain
unapplied native diffs while the proposal is under review; an implemented
change should not merge as canonical current architecture with a pending diff.

**Compatibility:** LikeC4 1.60.0 and earlier reject native diff syntax.
For consumers still pinned there, and for properties/views unsupported by native diffs, keep direct branch edits and the existing
C4Spec advisory source-bound `diff.py`/optional change-JSON route. Upgrade
per consuming repository after testing; don't silently change its version.

## Reusable committed native review

With the CLI and LikeC4 1.61.0, run from the consuming Git repository:

```bash
c4spec validate
c4spec review --model-dir architecture --base origin/main \
  --diff CHANGE_NAME --out /tmp/native-review
# Before the separately authorized native apply:
c4spec review --check-proposal /tmp/native-review/review.json
# After applying on the branch and committing the result:
c4spec review --check-applied /tmp/native-review/review.json
```

Use a new output directory outside the repository. Supply `--change` and
`--constraints-file` to `c4spec validate` only for existing records. The
report checks structure without executing consumer tests. For direct edits,
use `c4spec diff --base origin/main --json` and inspect the raw Git patch too.
CLI review reads committed model sources and local assets under the selected
directory (root models copy only model sources and config). Use the same
tool to create and verify its packet.

### Legacy review helper

For an existing installation without the CLI, run the shipped helper from its installed skill directory. `--base` is the
exact Git merge-base; the proposal must already be committed and model sources
must match HEAD. Use a new output path outside the repository.

```bash
python3 scripts/native_review.py --repo-root /path/to/project --model-dir architecture \
  --diff CHANGE_NAME --base <40-hex-merge-base> --out /tmp/native-review
# Before a separately authorized native apply, detect proposal drift:
python3 scripts/native_review.py --repo-root /path/to/project \
  --check-proposal /tmp/native-review/review.json
# After applying on the branch and committing the result:
python3 scripts/native_review.py --repo-root /path/to/project \
  --check-applied /tmp/native-review/review.json
```

The helper supports one pending named diff per packet, uses pinned 1.61.0,
validates before listing, copies only the model
sources/config into scratch, builds the native HTML and computes the expected
applied result there. Open `review-site/index.html`; inspect `source.patch` and
`semantic-diff.json`. The packet is unsigned local evidence, not approval.
External imports/assets are outside its copy boundary. Actual implementation
and tests remain the consuming project's responsibility.

Model/constraint checks need no change record:
`python3 scripts/check.py --model-json /tmp/model.json --repo-root /path/to/project`.
Pass `--change` only when an existing record is needed. This lints the exported
As-is model; for a native proposal also inspect the applied scratch export.

## Checks and limitations

Run `c4spec validate` with LikeC4 1.61.0. When using legacy helpers,
validate and export JSON with the consumer's pinned LikeC4 version. Run the
version-matched tools in the shared `c4spec` skill: `scripts/check.py` and
`scripts/diff.py`. The same skill contains the schemas, requirements and C4
guidance. This works with `npx skills add` and the optional
offline installer, even when only one agent is selected.
Use `--phase proposal` for planned references and `--phase completion`
for final references. **`check.py` validates schemas, paths, and model references; it never executes tests.** A passing `--phase completion` result is *not* behavioral verification. During `c4spec-verify`, run the actual test/contract commands, report commands and results against a revision/CI URL, and mark anything not run as **Not verified**. Do not treat `evidence.state=observed` as a synonym for test-file existence. An `observed` entry must carry `observedAt` (RFC 3339 timestamp) and a nonempty `note` explaining the measured event and provenance; this remains a **self-reported observation**, not authenticated test execution. For an existing source file alone use `declared`.

Native LikeC4 1.61.0 provides proposal-level visual change analysis.
The earlier C4Spec computed-model comparator remains an **advisory fallback**
for direct branch patches and post-apply source comparisons; do not substitute
it for a native pending-diff view (exported As-is can omit unapplied diffs).
Inspect the raw `.c4` patch and original view selectors as well. Never
auto-approve, auto-merge or deploy without explicit user authorization.

An unbound `diff.py` comparison is **exploratory**: it reports the delta but
binds no source snapshot. For review evidence, record paired provenance with
`scripts/provenance.py` and pass both artifacts back:

```bash
python3 scripts/provenance.py --model-dir architecture \
  --export /abs/base.json --git-commit <40-hex base> --compiler-version 1.59.4 \
  --compiler-command "npx --yes likec4@1.59.4 --version" --out /tmp/base-prov.json
python3 scripts/provenance.py --model-dir architecture \
  --export /abs/head.json --git-commit <40-hex head> --compiler-version 1.60.0 \
  --compiler-command "npx --yes likec4@1.60.0 --version" --out /tmp/head-prov.json
python3 scripts/diff.py --base /abs/base.json --head /abs/head.json \
  --base-provenance /tmp/base-prov.json --head-provenance /tmp/head-prov.json \
  --base-ref <40-hex base> --head-ref <40-hex head> --change c4spec/changes/<id>.json --repo-root .
```

Each provenance file records the sorted SHA-256 manifest of the `.c4`/
`.likec4` sources plus the LikeC4 project config in that directory, the exact
Git commit those bytes are verified against, the compiler version, whether an
executed command actually reported that version, and the SHA-256 of the
exported bytes. A Git-tracked export is rejected: generated exports are never
committed.

`--compiler-version` alone is a claim. `--compiler-command` runs a
producer-supplied command and records whether its output contained that
version. That is a **command-output match, not exporter proof**: the existing
export is never re-generated, so nothing binds it to the binary that printed
the version, and the field is an editable sidecar boolean. Reports therefore
say `exportBoundToCompiler: false` and keep the limitation visible.
Likewise, hashing only proves the paths a sidecar lists, so manifest
*completeness* is provable only against Git: with `--repo-root`, `diff.py`
re-enumerates the commit's sources, rejects an omitted or foreign entry, and
re-hashes every blob.

The report labels the two situations instead of blurring them:

- `reviewStatus: "exploratory"` — no paired provenance; no fingerprint.
- `reviewStatus: "source-bound-self-declared"` — the pair is complete and
  internally consistent, export bytes match, but Git was not consulted and the
  compiler version is caller-supplied.
- `reviewStatus: "source-bound-reverified"` — blobs were re-enumerated and
  re-hashed against both commits.
- `reviewAssurance.level` names `self-declared`, `git-verified` or
  `git-verified-compiler-reported`, with booleans for each checked fact,
  including `exportBoundToCompiler: false` in every case.

`diff.py` also fails closed on a partial pair, malformed or reordered
provenance, an export whose bytes changed after recording, a ref that
disagrees with the recorded commit, the same commit on both sides, and a
computed graph delta whose source manifests are identical.

The additive `reviewFingerprint` binds the normalized semantic diff, both
computed models, both manifests, commits, compiler versions, export digests
and the optional change-record hash. A source-only edit (comment or config
tweak) changes it even when the graph delta is empty; layout-only changes do
not. The pre-existing `fingerprint` stays model-only and unchanged. Neither is
a signature: `humanApprovalVerified` is always false, approval remains a human
decision, and coverage stops at the model directory — external imports,
deployment blocks and unexported view selectors are not bound.

### Offline review packet (optional)

`render_review.py` turns an existing `diff.py` report, an optional `check.py`
report and native LikeC4 PNGs into a temporary reviewer packet. It re-renders
nothing: no `.c4` parsing, no graph layout, no second model.

```bash
likec4 export png --filter recovery-prerequisites --flat -o /tmp/renders
python3 scripts/render_review.py --diff /tmp/diff.json --check /tmp/check.json \
  --change architecture/changes/my-change.json \
  --render recovery-prerequisites=/tmp/renders/recovery-prerequisites.png \
  --html /tmp/review.html --markdown /tmp/review.md
```

Pass the same `--change` to `diff.py` as well: only then are the record id
and SHA-256 part of `reviewFingerprint`. The adapter refuses a record whose
id or bytes no longer match `reviewBinding.change`, and marks a packet
unbound (with a warning) when the diff carries no binding.

`--change` adds the proposal record — intent, alternatives with the chosen one
marked, constraints, declared/planned evidence states and open questions — and
labels it as author-declared material. Behaviour-only and configuration-only
changes then read as "No C4 model delta … proposal record" instead of an empty
packet.

The HTML is self-contained: CSP `default-src 'none'`, no scripts, no remote
assets, every input string escaped, PNGs embedded as data URIs and horizontally
scrollable at full resolution. Outputs are scratch artifacts — never commit
them, never write under `architecture/`. Collisions, input overwrite and
non-PNG renders are refused.

Images are **caller-supplied**: only the PNG signature is validated, the origin
is not proven and no image is bound to an export (`renderAssurance.originVerified`
is always `false`). Treat a render as a reviewer aid, not evidence. Likewise
`testsExecuted` is a field of the supplied check report — `check.py` never runs
tests, so a `true` value is flagged as caller-supplied rather than trusted.
Markdown asset files are planned and validated (architecture guard, symlink,
input-overwrite, collision) before anything is written. Each artifact is written
through an exclusive, unpredictable same-directory temporary file and renamed into
place, so a pre-planted `.name.tmp` symlink is never followed; output or asset paths
that are themselves symlinks are refused. Atomicity is per file: a multi-file `--force`
run is not one transaction. A later failure removes artifacts this run created, keeps
pre-existing ones it already replaced, and reports both sets in a `status: partial`
error.

It shows the complete delta with before/after values, both fingerprints,
`reviewStatus`, `reviewAssurance` (including `exportBoundToCompiler:false`) and
`testsExecuted`. A view-only delta is stated as exactly that, so a newly added
view is never hidden behind "nothing changed". A changed view without a PNG, and
a PNG that matches no changed view, are both warned about. Markdown copies the
PNG beside itself so the summary stays self-consistent in scratch.

`alternatives` stays optional for routine behavior-only changes, but when
present the change schema requires at least three routes, and `decision` must
name one of them. Whether a change is consequential enough to need three
routes is a human reviewer judgement, not a schema verdict.
