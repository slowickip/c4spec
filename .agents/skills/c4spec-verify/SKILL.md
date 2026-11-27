---
name: c4spec-verify
description: Check that implementation, tests and the C4 model match a reviewed change.
license: Apache-2.0
---

# Verify the implemented change

Read the shared `c4spec` contract and the authoritative code, configuration
and model. Identify the reviewed proposal, implementation revision and
acceptance criteria before interpreting check results.
See the [model-first workflow reference](../c4spec-propose/references/model-first.md)
for model and constraint checks.

- **Model.** Validate with the project's pinned compiler. For a native proposal
  on LikeC4 1.61.0, run `c4spec review --check-applied <review.json>` against
  the committed result. Use `native_review.py` for packets created by that helper.
  Inspect changed source paths and confirm the intended proposal is no longer
  pending. For direct edits, compare the Git patch and computed models.
- **Behavior.** Locate the implementation and run the project's actual tests
  for each observable requirement. Record the command, revision and outcome.
  A completion check such as `check.py --phase completion` establishes
  structural evidence references. Test execution needs its own result.
- **Model and implementation alignment.** Check that the changed boundaries and
  interactions describe the implementation. Investigate old references,
  material drift and behavior the model leaves implicit.

When a durable constraint registry is supplied, compare required persistent
entries and verification references with the change and current model. Report
missing or stale obligations and whether the registry was checked.

Report confirmed results, failures and unverified requirements separately.
Send a material design divergence back to review. Use `c4spec-finish` when the
evidence covers the current implementation and the result is ready for human
review.
