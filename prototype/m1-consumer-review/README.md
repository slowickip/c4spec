# Test model review across four kinds of change

The runner creates a temporary Git repository from the [online shop example](../../examples/mini-project/README.md)
for each [case](cases/). It commits the base and proposed revisions, compiles
both with LikeC4 1.60.0, compares the exports, checks the change record, builds
the HTML and Markdown review packets, and runs the case’s Python tests.

| Case | Expected review result |
| --- | --- |
| Payment adapter | One added container, one relationship and one view. |
| Read retry budget | No architecture changes. Proposal checking accepts planned evidence. Completion fails while the referenced test is missing. |
| TLS configuration | The configuration changes on an existing relationship. The model diff is empty. |
| Payments audit view | One added view with the same elements and relationships. |

## Run the cases

From the repository root, with the [Python requirements](../../.agents/skills/c4spec/requirements.txt) installed:

```bash
review_output="$(mktemp -d)"
npm install --prefix "$review_output/tools" --no-save likec4@1.60.0
export LIKE4C4="$review_output/tools/node_modules/.bin/likec4"
python3 prototype/m1-consumer-review/rehearse.py --out "$review_output/cases"
python3 prototype/m1-consumer-review/probes/adversarial.py "$review_output/probes"
```

Read `matrix.md` for the results and open a case’s `review.html` to inspect its
proposal, evidence and diagrams. Use `--keep-repos` with `rehearse.py` to
inspect the generated Git revisions. The probes exercise source-only changes,
relationship direction, parallel relationships and missing evidence.

## Case manifests

Each `cases/*.json` file defines the model configuration, source edits,
additional files, views and change record. The runner checks the observed
element, relationship and view counts, finding codes, command exit statuses
and test counts against the manifest’s `expect` block. An unexpected pass in
a negative case fails the run.

The packet binds the change record and Git sources to their digests. Test
execution is reported separately from structural checks. Attached PNGs serve
as review aids. The packet does not authenticate their origin or the reviewer.
