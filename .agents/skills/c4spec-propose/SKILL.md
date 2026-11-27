---
name: c4spec-propose
description: Describe a change in the project's existing LikeC4 model and prepare it for review.
license: Apache-2.0
---

# Prepare a model proposal

Read the shared `c4spec` contract and the consuming project's `AGENTS.md`.
Read the [model-first workflow reference](references/model-first.md).
Identify the requested outcome and the model elements and behavior it affects.
Ask for clarification when the answer could change scope, compatibility or
acceptance. Reuse any existing branch for the same change after checking its
state. Record the Git merge base and follow the project's existing model layout.

## Record the change

- In LikeC4 **1.61.0**, express supported topology changes in a named
  native `diff` block in the existing model. Keep the current model As-is.
  Reference proposed elements from a focused view when that helps the review.
- Edit view definitions and existing element descriptions, technologies and
  titles directly in Git. Preserve element IDs. Projects on older compiler
  pins also use direct source review.
- For a behavior or configuration change with no architectural effect, leave
  the model as it is and report **zero C4 delta**. Capture acceptance in the
  project's code contracts or tests.
- Put the rationale and consequential alternatives in the PR or Git history.
  Use a per-change JSON record only for constraints or evidence that the
  existing sources leave unrepresented. Consider three viable routes for
  consequential architecture decisions.

## Prepare the review

Run the pinned compiler's validation. For a native proposal, inspect
`likec4 diff list --json` and `likec4 diff apply NAME --dry-run` and confirm
the working model stayed unchanged. Use `c4spec review` on the committed
proposal for the native view and scratch apply evidence. For direct edits,
show the source patch and computed comparison.

Report the branch, base and proposed commit, affected C4 IDs and
relationships, acceptance criteria, checks that ran and unanswered questions.
Hand the proposal to the human reviewer before applying it or implementing it.
