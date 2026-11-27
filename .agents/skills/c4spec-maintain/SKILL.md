---
name: c4spec-maintain
description: Review or update current-state C4 models and LikeC4 views when the user asks for diagram maintenance.
license: Apache-2.0
---

# Maintain C4 diagrams

Use this skill when the user asks for diagram work, for example “Check whether
the payments view still matches the code” or “Update the container diagram
after the queue migration.” Read the sibling `c4spec` skill's shared contract,
C4 governance and relevant LikeC4 references. Follow the project's instructions,
model layout and compiler pin. Its existing development workflow owns
proposals, requirements and implementation.

## Inspect the model and evidence

- Identify the view's audience, question and system boundary. Inspect its
  selectors and the underlying elements and relationships they project.
- Check relevant code, contracts, configuration and available runtime evidence.
  Compare with the implementation at the revision being documented, including
  implemented changes on the current branch. Treat plans, old comments and
  ambiguous source as leads. Report unresolved discrepancies with their
  sources and keep the model unchanged where the evidence is inconclusive.
- For a review-only request, report findings and the affected views or IDs
  without editing. If the model already tells the right story, report that it
  needs no edit.

## Make a focused diagram edit when requested

- Use context and container views by default. Show significant boundaries,
  responsibilities and directed interactions. Add a component, dynamic or
  deployment view only when it answers a concrete question at that scope.
- Edit the existing view selectors when the underlying graph is accurate.
  Correct or extend the canonical graph when the architecture facts themselves
  have changed. Preserve stable element and view IDs where identity survives.
- Edit current-state LikeC4 sources directly in Git. Leave pending native
  proposals and OpenSpec artifacts to the project's development workflow.
  Keep speculative future architecture out of the current model.

## Check and present the result

- Run the project's model check with its pinned compiler. Use
  `c4spec validate --model-dir <path>` if the CLI is available and matches the
  project pin, or the project's pinned `likec4 validate <path>`.
- Preview affected views, including views that reuse edited graph facts. Read
  the Git source diff to check selectors and confirm the scope. For committed
  changes, use `c4spec diff --base <base-ref>` when available.
- Report the affected views, evidence, checks run and open questions. If the
  project has the C4Spec GitHub Actions workflow installed, it compares the
  rendered diagrams from the committed PR revisions and presents changes
  independently of how the model edit was authored.
