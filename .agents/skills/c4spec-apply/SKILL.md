---
name: c4spec-apply
description: Implement a reviewed C4Spec design and apply its model changes with explicit authorization.
license: Apache-2.0
---

# Implement the authorized change

Read the shared `c4spec` contract. Establish which proposal revision and
implementation scope the user authorized. Review the model patch, applicable
constraints and acceptance criteria. Keep progress in Git and the project's
existing records.
See the [model-first workflow reference](../c4spec-propose/references/model-first.md)
for native apply and verification commands.

With a native proposal on LikeC4 **1.61.0**, run
`c4spec review --check-proposal <review.json>` before implementation. Use
`native_review.py --check-proposal <review.json>` for a packet made by that
helper. For direct model edits, compare the approved source patch and computed
delta. Return to review when the intended behavior, architecture or reviewed
proposal changes. Report blockers that make the approved scope infeasible.

## Advance the model with the implementation

Implement the authorized behavior in the governing code or configuration and
exercise its tests. When the revised architecture describes that result,
validate and rehearse `likec4 diff apply NAME --dry-run`. Inspect all paths
the compiler would edit and compare them with the reviewed proposal. Resolve
any drift or overlaps with the reviewers, leaving the proposal pending until
then.

Apply the native diff on the feature branch. Validate the resulting model and
inspect and commit all compiler edits, including changes outside the file
containing the proposal. Preserve the rationale in Git and verify that
references still resolve. Projects using direct edits continue with the
reviewed Git changes.

Hand off to `c4spec-verify` with the implemented scope, test results and
remaining questions. Deployment and merge require their own authorization.
