---
name: c4spec-explore
description: Investigate a design question using the project's C4 model, source and evidence.
license: Apache-2.0
---

# Investigate a design question

Read the shared `c4spec` contract and the project instructions. Use the current
LikeC4 model to locate the relevant system boundary and paths through it.
Inspect the code, tests, contracts or configuration that govern the behavior
in question.

Establish what is already true, what the user wants to change, and which
assumptions would affect the outcome. Resolve repository facts from evidence
before asking the user. Ask a focused question when a choice about scope,
behavior or compatibility depends on their answer.

For a significant design decision, compare at least three viable approaches
against the actual constraints. Use an existing view or a small diagram to
explain a boundary, interaction or failure path when it helps the discussion.
Identify the evidence behind each recommendation and point out uncertainty.

Keep exploration read-only. The discussion can end with a decision, a
recommendation or an open question. When the user wants to record a design
in the repository, use `c4spec-propose`.
