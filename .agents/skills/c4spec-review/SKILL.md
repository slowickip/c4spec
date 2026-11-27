---
name: c4spec-review
description: Review a proposed model change against its baseline, constraints and implementation evidence.
license: Apache-2.0
---

# Review the proposed architecture

Read the shared `c4spec` contract. Identify the reviewed base and proposal
commits. Compare the changed source and its intent with the original model,
the current implementation and any behavior constraints.
See the [model-first workflow reference](../c4spec-propose/references/model-first.md)
for review commands and evidence requirements.

## Inspect the model delta

On LikeC4 **1.61.0**, validate the model before listing native proposals.
For a named proposal, use `c4spec review` to build the As-is, Changes and
To-be views from committed inputs. Check the raw patch and
`likec4 diff apply NAME --dry-run` output as well. Inspect changes to IDs,
directed relations, cascaded removals and affected views. Confirm that
previewing left the proposal sources intact. Leave overlapping proposals
pending until their owners settle the overlap.

For direct property or view edits and older compiler pins, compare the raw
Git patch and computed base and head models. Keep existing IDs for the same
architectural elements. Check authored selectors and other source details
that the computed comparison can omit.

## Resolve discrepancies

Point out where model, code, constraints or observed evidence disagree.
Check whether a discrepancy calls for a change to the proposal or to the
planned implementation. When the user authorizes a design revision, edit
the authoritative source, rerun validation and produce review evidence for
the new commit.

Report the reviewed revision, changes by element and relationship, unresolved
questions and where to inspect the views. Leave the approval decision with the
human reviewer.
