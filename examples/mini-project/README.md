# Online shop example

The [shop model](architecture/shop.c4) shows a customer, a Python API and a
PostgreSQL database. The RabbitMQ broker and notification worker illustrate a
proposal. The example implements cache behavior and database configuration in
Python. The worker exists only in the model.

## Read the diagrams

Both views show the shop at container level (L2). Open `shop-overview` for the
API and its dependencies, or `notifications` to trace an order event from the
API through the broker and worker to the customer. The shop defines the L1
system boundary. Cache fallback and expiry are internal API behavior.
[C4 modeling guidance](../../docs/c4-governance.md)

## Run the checks

From `examples/mini-project/`, run the tests and compile the model.

```bash
python3 -m unittest discover -s tests -v
npx --yes likec4@1.60.0 validate
```

| Change | What to check |
| --- | --- |
| [Cache fallback](c4spec/changes/add-cache.json) | A cache hit avoids the database. A miss or cache failure falls back to the database. Database errors propagate. |
| [Cache expiry](c4spec/changes/expire-cache-entries.json) | Unit tests exercise the lifetime of entries in the order cache. |
| [Database TLS](c4spec/changes/require-tls-for-db.json) | Tests validate connection configuration, including conflicting `sslmode` values. A live TLS handshake requires a database. |
| [Notification worker](c4spec/changes/add-notification-worker.json) | The proposal adds a broker, a worker, three relationships and the `notifications` view. Completion checking should fail while the worker test is only planned. |

To check the cache fallback record against the model and its registered constraint,
install the [Python requirements](../../.agents/skills/c4spec/requirements.txt)
and run the following commands from the same directory.

```bash
shop_output="$(mktemp -d)"
npx --yes likec4@1.60.0 export json --skip-layout -o "$shop_output/model.json"
python3 ../../.agents/skills/c4spec/scripts/check.py --model-json "$shop_output/model.json" \
  --change c4spec/changes/add-cache.json --constraints-file c4spec/constraints.json \
  --repo-root . --phase completion
```

The checker resolves evidence paths and constraint IDs. The unit tests above
exercise the behavior with in-memory dependencies.

## Compare model revisions

Export both sides with the same compiler. Use the [baseline models](fixtures/README.md)
to inspect the notification proposal or check that a behavior-only change has
an empty model diff. To compare the notification proposal from this directory:

```bash
shop_diff="$(mktemp -d)"
mkdir -p "$shop_diff/base/architecture"
cp fixtures/before-notifications.c4.fixture "$shop_diff/base/architecture/shop.c4"
(cd "$shop_diff/base" && npx --yes likec4@1.60.0 export json --skip-layout -o "$shop_diff/base.json")
npx --yes likec4@1.60.0 export json --skip-layout -o "$shop_diff/head.json"
python3 ../../.agents/skills/c4spec/scripts/diff.py --base "$shop_diff/base.json" --head "$shop_diff/head.json"
```

For a named native proposal on LikeC4 1.61.0, see the
[worker replacement example](../../prototype/native-diff-first/README.md).
