---
name: c4spec-finish
description: Prepare the C4Spec feature branch for normal GitHub review and merge without a separate specification archive/synchronization step.
license: Apache-2.0
---

Read the shared `c4spec` contract, the pinned Git merge-base, the
canonical `.c4` source diff, any project-local change/constraint record,
and the actual implementation/test evidence.

## Before proposing a normal merge

- Reconcile architecture, source code/IaC, durable constraints and real test
  outcomes. Show the reviewer which checks executed and which were not run.
- If newly proposed C4 containers/relationships still have **only planned
  evidence**, the branch is a **design proposal, not merge-ready implemented
  architecture**. Keep its PR as a draft; do not silently let the to-be model
  become the current model on `main`.
- A documentation correction that accurately reflects already-existing code
  may be complete without new implementation, but establish that with source
  evidence and human review; don't claim runtime observation from YAML.
- With LikeC4 1.61.0 native diff workflow, inspect `diff list` before merging
  an **implemented** architecture change: the reviewed named diff should have
  been applied, with its temporary block removed and the real model updated.
  Do not merge an unapplied to-be diff as current implemented architecture.
  A deliberately design-only PR retaining a diff needs explicit separate
  owner acceptance and should never be represented as production conformance.
- Preserve material design rationale in PR/commit history because native
  apply discards diff titles and comments. Git records the transition to the
  implemented model. Carry forward durable non-topological constraints when
  the existing tests and contracts leave them unrepresented.

Prepare the normal GitHub PR with a concise review summary, raw `.c4` patch,
advisory computed diff, actual tests and known gaps. **The human owner decides
whether it can merge.** Do not auto-merge or deploy. After an authorized
merge, the canonical model and implementation advance together.
