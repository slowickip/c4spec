---
name: c4spec-continue
description: Recover the state of an existing C4Spec change and identify the next step.
license: Apache-2.0
---

# Recover a change from Git

Read the shared `c4spec` contract. Use the change named by the user or evident
from the current branch and discussion. If the repository has several plausible
changes, summarize their states and ask which one to resume.

Read the branch and its PR, the source patch, optional constraint records and
the latest review and test results. On LikeC4 **1.61.0**, check
`likec4 diff list --json` for pending proposals after validating the model.
Compare the commit history and current model to establish whether a proposal
was applied and which checks still describe the current revision.

## Select the next action

| Repository evidence | Next action |
| --- | --- |
| An agreed change needs a proposal | Use `c4spec-propose` |
| A proposal needs review or moved since review | Use `c4spec-review` |
| The user authorized implementation and work remains | Use `c4spec-apply` |
| Implementation has changed since the last verification | Use `c4spec-verify` |
| Evidence covers the current revision and the change is ready for PR review | Use `c4spec-finish` |
| Scope, approval or evidence is unresolved | Explain what is missing |

Give one next action, the current revision and the evidence supporting that
choice. The skills are discoverable instructions. Use the agent's supported
way of invoking them.
