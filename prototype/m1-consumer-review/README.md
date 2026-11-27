# M1 consumer review + visual workflow prototype

Scratch-only rehearsal of the C4Spec reviewer chain on four realistic consumer
changes. The harness builds disposable Git repositories from
`examples/mini-project`, commits a base and a head revision per case, and runs
the real tools: released LikeC4 1.60.0 `validate`/`export`, `provenance.py`,
`diff.py`, `check.py` and `render_review.py`.

Nothing generated here is committed or treated as architecture source. The case
manifests are data: an edit whose anchor does not match the base text fails the
run instead of drifting silently.

## Commands

```bash
python3 prototype/m1-consumer-review/rehearse.py --out "$SCRATCH/m1-rehearsal"
python3 prototype/m1-consumer-review/probes/adversarial.py "$SCRATCH/m1-probes"
python3 -m unittest discover -s tests          # full Python suite
python3 -m unittest discover -s examples/mini-project/tests
```

`rehearse.py` writes `matrix.json`, `matrix.md`, and per case `review.html`,
`review.md`, `artifacts/` (exports, provenance, diff, check reports, PNG).
`--keep-repos` preserves the disposable repositories for inspection.

## Four-case matrix (one representative run; SHAs and digests are per run, LikeC4 1.60.0, measured)

| Case | Scenario | Δ E/R/V | base → head | model-only | review | proposal | completion | scenario tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Architecture: payment adapter container, directed relation and focused view | 1/1/1 | `5bfc72e268` → `4b19cafec4` | `ec112a53ac45` | `f91d924c24cf` | 0 (0e/0w) | 0 (0e) | 25 tests |
| B | Behavior-only: read retry budget with declared and planned evidence | 0/0/0 | `d2a0ff0bb8` → `92e9c4487a` | `6df4abcf2652` | `f516cca075ef` | 0 (0e/1w) | 1 (2e) | 26 tests |
| C | Configuration-only: per-environment TLS mode table | 0/0/0 | `8d7d254870` → `4666aef9f6` | `6df4abcf2652` | `e779b61e2881` | 0 (0e/0w) | 0 (0e) | 27 tests |
| D | View-only: focused audit view, zero element/relationship delta | 0/0/1 | `76b8725731` → `dc06a3696b` | `4926af89a741` | `6f4f90cf22be` | 0 (0e/0w) | 0 (0e) | 22 tests |

Reading the matrix:

- **A** changes one container, one directed relation and adds a focused view;
  proposal and completion are clean.
- **B** changes behaviour only: zero model delta, one warning in proposal
  (`planned_path`) and completion fails with `still_planned` + `missing_path`
  because one evidence path is honestly planned, not written.
- **C** changes configuration only: zero model delta and no invented topology.
- **D** adds one view with zero element/relationship delta — the #350 pattern —
  and the packet says "1 view(s)" rather than "nothing changed".

## Adversarial probes (disposable revisions, real scripts)

| Probe | Δ E/R/V or exits | model-only | review | pass |
| --- | --- | --- | --- | --- |
| E-comment-only | 0/0/0 | `6df4abcf2652` | `cb700f8a3958` | yes |
| F-selector-order | 0/0/0 | `6df4abcf2652` | `793e66a04c10` | yes |
| G-reversed-direction | 0/2/3 | `79daf76f58b9` | `99cb396c1199` | yes |
| H-parallel-relation | 0/1/1 | `09dd4792e761` | `7d65eef51971` | yes |
| I-planned-missing-path | proposal 0 / completion 1 | codes: planned_path | completion: missing_path, still_planned | yes |
| I-declared-missing-path | proposal 1 / completion 1 | codes: missing_path | completion: missing_path | yes |

Facts the probes establish:

- A comment-only edit and a view-selector reordering both produce **zero**
  semantic delta while the **review fingerprint changes** — a model-only
  checksum cannot see them, the source-bound fingerprint can.
- Reversing a relationship direction is reported as a removal plus an
  addition, never as a silent modification.
- Adding a parallel relation (same endpoints, different statement) is detected
  as exactly one added relation; the two compiles produced **identical**
  relation ids in this probe, so id churn is not universal.
- A `planned` path is a proposal warning and a completion failure; a `declared`
  path that does not exist fails the proposal too.
- Relation-level edits also mark the computed views that contain them as
  `modified` (G, H). That is LikeC4 view content, not an authored view edit; the
  packet lists it under view changes, so a reviewer must read the field changes.

## What the harness now enforces

Every case must declare a **complete** `expect` block in its manifest. A case
with no block, an empty one, a partial one or an unknown key is refused before
any work starts, so deleting the expectations cannot silently disable them. The
rehearsal then fails closed on any deviation:

- exact E/R/V delta, proposal exit and finding codes by severity, completion
  exit and error codes — so B's *intentional* `still_planned`/`missing_path`
  completion failure is expected, while a formerly failing case turning green
  is a failure too;
- render exit `0` and a non-empty packet;
- scenario tests **executed inside the disposable repository**
  (`python -m unittest discover -s tests`), with the exact test count per case
  (22 base, 25 with the payment fixture, 26 with the retry fixture, 27 with the
  TLS fixture) and exit `0`;
- `reviewStatus == source-bound-reverified` and the change record's id/SHA-256
  bound in `reviewBinding.change`;
- the compiler row comes from actually running `<cli> --version`: the observed
  version and its exit code are recorded and must equal the requested pin
  (`1.60.0`). A CLI that reports another version aborts the case before any
  evidence is written; the matrix never copies the requested pin into the
  observed slot. `exportBoundToCompiler` stays `false` — a version string is
  not compiler provenance.

`outcome_violations()` is unit-tested without LikeC4, including the negative
case: an unexpected render/test/completion outcome makes `main()` exit `1`,
while B's expected negative completion keeps the run green.

`rehearse.py` passes the same `--change` to **both** `diff.py` and
`render_review.py`. The review fingerprint therefore covers the change-record
bytes, and the adapter refuses to render a record whose id or SHA-256 does not
match the diff it was given. A packet whose diff carries no binding says so in a
red banner and in the warnings, instead of showing a proposal beside an
apparently coherent fingerprint.

## Reviewer experience notes

- The offline packet renders the proposal record (intent, alternatives with the
  chosen one marked, constraints, evidence states, open questions) next to the
  semantic inventory. Before this prototype the adapter showed only diff and
  check output, so a behavioural or configuration-only change had no visible
  content at all.
- A model-free change is now described as "No C4 model delta … proposal record"
  instead of "no semantic delta"; a view-only change still names the added view.
- Impeccable flags are preserved: `exportBoundToCompiler:false`,
  `humanApprovalVerified:false`, `renderAssurance.originVerified:false` and the
  `testsExecuted` self-reported banner.

## Limits

- Structural checks only: `check.py` never executes the fixture tests named in
  the evidence, and the packets say so — even though the rehearsal *does* run the
  scenario tests separately and records their exit codes and counts.
- Case A's payment adapter is a fixture, not a deployed container; a clean
  structural completion is not deployment conformance.
- Images are caller-supplied; only the PNG signature is validated and no image
  is bound to an export.
- The rehearsal uses `/tmp`-style scratch repositories; absolute paths, commit
  SHAs and fingerprints in a generated matrix are per run, not constants.
- Completion cannot distinguish `declared` from `observed` evidence; a human
  still has to decide whether any evidence was actually produced.
- No runtime, cluster, production or CI claim is made anywhere in this tree.

## Case manifest contract

Each `cases/<slug>.json` is the whole recipe; nothing about a case lives only in
the harness:

- `id`, `slug`, `title`, `change` (path to the change record in the head tree)
- `likec4Config` — written to `architecture/likec4.config.json` in the base
  fixture. `examples/mini-project/` ships no LikeC4 config, so without this the
  export has `projectId: default`; the rehearsal names it `mini-shop`.
- `changeRevision: "head"` and `checkModel: "head"` — the harness only
  implements those values and fails on anything else. The change record
  describes the proposal, so it is committed with the head; both check phases
  evaluate the head export, because that is the model the change proposes.
- `edits` — `{path, find, replace}` or `{path, append}`; a `find` anchor must
  match exactly once or the run aborts.
- `files` — new files copied from `files/` into the tree.
- `views` — view ids whose native PNG is exported and rendered.

## Blind handoff (independent subagent, no Slack context)

A subagent was given only the Git repository, issue #15 and the skill docs, and
rebuilt the view-only case by hand in its own scratch repository.

| Fact | Blind result | Harness result |
| --- | --- | --- |
| delta | 0 elements / 0 relationships / 1 view (`payments-audit`) | same |
| model-only fingerprint | `sha256:4926af89a741…` | `sha256:4926af89a741…` |
| review fingerprint | `sha256:630f5364ca46…` (its own commits) | differs per commit |
| `reviewStatus` / level | `source-bound-reverified` / `git-verified-compiler-reported` | same |
| `exportBoundToCompiler` / `humanApprovalVerified` | `false` / `false` | same |
| proposal / completion | exit 0 (0e/0w) / exit 0 (0e/0w) | same |
| PNG | 87 KB, signature OK | rendered and inspected |

The handoff passed: it reproduced the scenario end to end without hidden
context. It also exposed two real gaps, both fixed here:

1. the LikeC4 config was created by the harness but never declared, so a blind
   consumer could not know it existed (and got `projectId: default` without it);
   now every manifest declares `likec4Config`;
2. the manifests never said which revision the change record belongs to or
   which export `check.py` reads; both are now explicit (`changeRevision`,
   `checkModel`) and the harness rejects unsupported values.

One upstream quirk it reported, verified separately: with a named config,
`likec4 export json` emits **two byte-identical project entries with the same
`projectId`** ("Found 2 projects: mini-shop + default"). `provenance.py`
dedupes `projectIds`, `diff.py` treats them as one project and the export is
deterministic, so nothing fails — but project identity in that file is
ambiguous. Whether c4spec should pin or reject that shape is a design decision,
not something to change silently.

## Keep / improve / defer

- **Keep:** the four-case harness, the adversarial probes, the `--change`
  packet section, the refusal to compare identical commits, the declared
  manifest contract.
- **Improve (small):** surface the completion-phase result next to the proposal
  result in the packet; label relation-induced view modifications explicitly.
- **Defer:** any automatic evidence verification, image signing, multi-commit
  history view, a new renderer, or rejecting duplicate project entries — each
  needs an owner decision.

Three options for the next design decision (completion visibility):

1. Accept a second `--check-completion` input and render both phases side by side.
2. Keep one report per packet and require the reviewer to run completion separately.
3. Emit a compact phase summary from `check.py` itself and consume that.

Three options for the duplicate-project shape:

1. Leave it: provenance dedupes, diff collapses, exports stay deterministic.
2. Reject exports whose projects share one `projectId` (fail closed, may break
   valid upstream output).
3. Record the raw project count in provenance and warn when it exceeds one.
