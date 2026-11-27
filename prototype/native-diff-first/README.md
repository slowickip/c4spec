# Review a notification worker replacement

This example adds a named `replaceNotifications` diff to a temporary copy of
the [online shop model](../../examples/mini-project/architecture/shop.c4).
LikeC4 1.61.0 shows how replacing the worker affects the existing views.

## Open the proposal

Run from the repository root:

```bash
worker_demo="$(mktemp -d)"
python3 prototype/native-diff-first/rehearse.py --out "$worker_demo/review"
cd "$worker_demo/review/proposal"
npx --yes likec4@1.61.0 start
```

Open `shop-overview` or `notifications`. Select **Replace the notification
consumer** in the model state menu and switch between **As-is**, **Changes**
and **To-be**. Red shows removals and green shows additions.

## Inspect the result

- `proposal/architecture/shop.c4` contains the named diff.
- `dry-run.txt` shows the compiler’s preview. `applied/architecture/shop.c4`
  contains the result of applying it in a separate directory.
- `stale-reference/` and `overlapping/` exercise rejection of invalid removals
  and conflicting proposals. `summary.json` records the outcomes.

The [GitHub Actions workflow](../../.github/workflows/native-diff.yml) publishes
the interactive viewer and source files in the `native-diff-as-is-changes-to-be`
artifact for seven days. Open `review-site/index.html` in the extracted artifact.

The Actions summary includes a Mermaid diagram when its per-view counts
match LikeC4’s. It supports up to two views, with at most 40 nodes and 80
edges per view. Ambiguous parallel relationships, conflicting containment or
unsupported views can prevent an inline diagram. The native viewer includes
the full layout and styling.

For a proposal in your own project, follow the
[consumer guide](../../docs/consumer-guide.md#native-proposal-and-review).
