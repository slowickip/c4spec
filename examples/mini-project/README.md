# Example project

This is an intentionally **mixed-state teaching fixture**, not a deployed
system. It contains one software system (`shop`), a customer, an API and a
PostgreSQL container, plus a **proposed** RabbitMQ message broker and
notification worker. This is a **legacy fixture** with a mixed-state
graph, not proof that those services exist. It was merged into the tool
repository as a teaching example and must never be presented as a deployed
system. New architecture proposals on LikeC4 1.61.0 should use a **native
named diff in the same `.c4` source on a Git branch**, leaving As-is nodes
unchanged until apply; see the [native 1.61 replacement-worker pilot](../../prototype/native-diff-first/README.md).
Standalone baselines in [fixtures](fixtures/README.md) support tests of the
1.60-era comparator.

## Reading the example by C4 level

C4 levels are **zoom levels**, not phases of the C4Spec workflow. Open [`architecture/shop.c4`](architecture/shop.c4) in LikeC4 and use this map:

| Level | What the example models | What to look for |
| --- | --- | --- |
| **L1 — System Context** | `shop` is the **Online Shop software system**; `customer` is a person outside that boundary. | The system boundary is defined, but this fixture does **not** author a dedicated L1 system-context view. An L1 diagram would show the shop as one box and its actors/external systems, not the internal API. |
| **L2 — Container** | `shop.api` (Python API), `shop.db` (PostgreSQL), plus **proposed** `shop.broker` (RabbitMQ) and `shop.worker` (Python consumer). | `shop-overview` displays **L2 — Online Shop: container overview**; `notifications` displays **L2 — Order notifications: asynchronous delivery path**. Both show L2 containers (and the customer). These views do **not** imply the proposed services are running. |
| **L3 — Component** | **Not modeled intentionally.** | The cache fallback in `app/product_reads.py` and cache expiry in `app/order_cache.py` concern behavior inside `shop.api`, but don't automatically justify separate C4 components. Model the API's internal logical components only if an actual architectural question requires that depth. |
| **L4 — Code (optional)** | The Python files and executable unit tests. | Implementation/test evidence, not automatically C4 nodes or a reason to maintain class diagrams. |

**Elements and views are different:** declaring `shop = system` establishes a software-system element, not a finished L1 diagram. Likewise, `shop.api = container` does not mean an OS, Docker or Kubernetes container. Here, both authored views explicitly start their visible LikeC4 `title` with `L2 —`; their stable IDs (`shop-overview` and `notifications`) remain unchanged. The rehearsal's additional `checkout-path` and `payments-audit` views use the same L2 prefix. See the [C4 level definitions](../../.agents/skills/c4spec/references/c4-governance.md) for rules applicable to real projects.

The four optional JSON records below are **historical acceptance fixtures**
for behavior/config traceability and the older direct-edit workflow.
They are *not* an instruction to create one JSON file for every new change.
Architecture-only work should usually need only a native `diff` block plus
the Git PR; detailed behavior stays in executable contracts/tests.

These four records have deliberately different states:

| Change record | Status in this example | Evidence |
| --- | --- | --- |
| `add-cache.json` | **Implemented fixture behavior** (apply → verify → finish case) | `app/product_reads.py` and 8 passing unit tests in `tests/test_cache_fallback.py`; `cache-fallback` promoted to `c4spec/constraints.json`; zero `.c4` delta |
| `expire-cache-entries.json` | **Implemented fixture behavior** | `app/order_cache.py` and 6 passing unit tests; not production |
| `require-tls-for-db.json` | **Implemented config fixture** | `app/db_config.py` and 8 passing unit tests; no live DB TLS handshake |
| `add-notification-worker.json` | **Proposed architecture only** | Broker and worker appear in `.c4` *to-be* graph but have no implementation, deployment or executable notification test |

The TTL cache (`app/order_cache.py`) and the read-path fallback
(`app/product_reads.py`) are separate fixtures for separate constraints; neither
is production code. `check.py` verifies structural references; passing it does
not execute any behavioral test.

Exercise the workflow:
- Read `architecture/shop.c4` with the LikeC4 extension and identify whether
  you are reviewing current code or proposed architecture.
- Use `c4spec-propose` on a Git branch, editing the canonical graph **only if**
  an architectural boundary/relationship actually changes. A behavior-only
  change can have zero `.c4` edits.
- Use pinned LikeC4 `validate`, `export json`, the bundled `diff.py`, and
  the **raw Git `.c4` patch**. LikeC4 `diff { ... }` syntax is *not released*
  in the pinned 1.60.0 version; do not put it in this example.
- Apply only after explicit approval; execute real tests separately from the
  structural checker and never claim runtime verification for this fixture.

Stable initial IDs are `shop`, `shop.api`, `shop.db`; proposed IDs
`shop.broker` and `shop.worker` remain in this explicitly mixed-state teaching fixture on main; neither is implemented.

## Applied case: cache fallback (apply → verify → finish)

`add-cache` started as a proposal with a `planned` test reference and is now a
completed fixture change. The read path tries the cache first and falls back to
the database whenever the cache misbehaves:

```bash
python3 -m unittest discover -s tests -v                 # 22 tests: 8 cache-fallback + 14 others
npx --yes likec4@1.60.0 validate                         # Valid (1 files)
npx --yes likec4@1.60.0 export json --skip-layout -o /tmp/model.json
python3 ../../.agents/skills/c4spec/scripts/check.py --model-json /tmp/model.json \
  --change c4spec/changes/add-cache.json \
  --constraints-file c4spec/constraints.json --repo-root . --phase completion
```

Expected: `exit 0`, `valid: true`, `errors: 0`, `testsExecuted: false`. The
completion check proves the evidence **paths** exist and the constraint is
registered; the behaviour claim rests on the executed suite, not on the checker.

What the fixture proves and does not prove:

- positive: a cache hit is served without touching the database; a miss reads it;
  `RuntimeError`, `TimeoutError` and `OSError` from the cache all fall back;
- negative: a database failure propagates instead of being masked, an unknown
  product raises `ProductNotFound` instead of returning an empty row, and a
  returned row is a copy rather than shared mutable state;
- not proven: real latency improvement, real PostgreSQL behaviour, cache client
  semantics, or anything about a deployed system. `InMemoryProductDb` and
  `FakeCache` are test doubles.

`cache-fallback` was promoted to `c4spec/constraints.json` because it is durable
and testable; the change record keeps its own copy so the proposal still reads
standalone. Zero `.c4` delta is expected here: the cache is an implementation
detail of `shop.api`, not a container.


## Reproduce the architecture before and after

From `examples/mini-project/`, use the standalone pre-proposal test fixture.
Copy it to a temporary model directory for compilation.

```bash
TMP="$(mktemp -d)"
mkdir -p "$TMP/architecture"
cp fixtures/before-notifications.c4.fixture "$TMP/architecture/shop.c4"
(cd "$TMP" && npx --yes likec4@1.60.0 export json --skip-layout -o "$TMP/base.json")
npx --yes likec4@1.60.0 validate
npx --yes likec4@1.60.0 export json --skip-layout -o "$TMP/head.json"
python3 ../../.agents/skills/c4spec/scripts/diff.py --base "$TMP/base.json" --head "$TMP/head.json"
git diff --no-index "$TMP/architecture/shop.c4" architecture/shop.c4
```

Expected: added `shop.broker` and `shop.worker` with responsibilities and
technology, three relationships, and a focused `notifications` view. The
generated `index` view may also change, but that doesn't necessarily imply
a separately authored view change. Preserve the raw `.c4` source diff in review.

**Important:** these two exports compare the *design proposal*, not the
implemented Python fixture. To test behavior-only/config-only changes with
zero architecture delta, compare their actual branch base/head `.c4` revisions;
a self-diff of the same JSON file is only a smoke test of the comparator.

## Behavior-only change: no `.c4` edit at all

`c4spec/changes/expire-cache-entries.json` is a **structurally completed** behavior-only
change; the checker does not run tests. It bounds cache staleness for `shop.api` without adding a single node:
the cache is an implementation detail, not a container, so the canonical model
is untouched and the semantic diff is empty. The obligation lives in one
constraint with an executable check:

```bash
python3 -m unittest discover -s tests -v          # 22 fixture tests, including 6 TTL tests
npx --yes likec4@1.60.0 export json --skip-layout -o /tmp/model.json
python3 ../../.agents/skills/c4spec/scripts/check.py --model-json /tmp/model.json \
  --change c4spec/changes/expire-cache-entries.json \
  --constraints-file c4spec/constraints.json --repo-root . --phase completion
```

`app/order_cache.py` is a fixture reference implementation, not production code
(the directory is `app/`, not `code/`, to avoid shadowing Python's stdlib module).

Watch the proposal/completion split: set `evidence[0].state` back to `"planned"`
and remove `tests/test_order_cache.py`. Then `--phase proposal` exits 0 with two
`planned_path` warnings, while `--phase completion` exits 1 with `still_planned`
plus `missing_path` for the record and for the constraint reference. Nothing in
either phase asks for a model change — that is the point of the case.

The tests are not vacuous: raising `MAX_TTL_SECONDS` to 400 makes multiple
tests fail. Structural `check.py --phase completion` can still return valid,
because it only checks references; **run the test command and record the actual
result and revision** before claiming behavior has been verified.

## Config-only change: TLS on an existing relationship, zero C4 delta

`c4spec/changes/require-tls-for-db.json` is a **config-only** change with a
security consequence: `shop.api -> shop.db` must use TLS and must not fall back
to plaintext. Nothing structural moves — transport encryption is a property of
the existing relationship — so the graph stays untouched and the semantic diff is
empty.

The record asks the structural question out loud instead of asserting "no impact":
it lists three alternatives (`model-tls-terminator`, `relabel-relation-technology`,
`config-only-constraint`), selects one, and keeps an open question about
certificate-chain verification (`require` vs `verify-full`).

```bash
python3 -m unittest discover -s tests -v          # 22 fixture tests, including 8 TLS config tests
npx --yes likec4@1.60.0 export json --skip-layout -o /tmp/model.json
## For a real branch comparison, export the model from its Git base and head.
## A self-diff is only a comparator smoke test, not proof of zero architectural impact:
python3 ../../.agents/skills/c4spec/scripts/diff.py --base /tmp/model.json --head /tmp/model.json
python3 ../../.agents/skills/c4spec/scripts/check.py --model-json /tmp/model.json \
  --change c4spec/changes/require-tls-for-db.json \
  --constraints-file c4spec/constraints.json --repo-root . --phase completion
```

Expected: the diff reports no added or modified elements and no relationship
changes; completion exits 0 with `testsExecuted: false`, `runtimeVerified: false`.
`check.py` validates structure only, has no security rules, and does not run
tests — "no findings" is not a security verdict. The verdict is the executed test
suite plus the reasoning in the record.

`app/db_config.py` is a fixture configuration surface (`build_dsn`, `assert_tls`),
not a production data layer or proof of a live TLS handshake. Its parser
rejects duplicate `sslmode` values that could otherwise conceal a plaintext
fallback. Two measured caveats for reviewers:

- editing the relation technology on a uniquely matched relationship is now shown
  in `relationships.modified[].fieldChanges`, not as topology churn. Ambiguous
  parallel relationships still appear as removed/added, requiring manual review;
- adding an invented node (`TLS terminator`) is reported by `diff.py` as
  `shop.tls` plus two relations, while `check.py` still returns `valid: true`
  with zero findings. The guard against invented nodes is the reviewer.

## Proposed architecture change: async notifications (nothing implemented)

`c4spec/changes/add-notification-worker.json` is the **proposed, unimplemented** architecture case. It adds
two proposed containers to the example's branch-versioned C4 graph — `shop.broker` (an independently running RabbitMQ message broker,
not an individual queue resource) and `shop.worker` (runnable consumer) — three directed
relationships, and one focused view:

```
shop.api    -> shop.broker  'Publishes order events'      'AMQP'
shop.broker  -> shop.worker 'Provides order events for consumption'     'AMQP'
shop.worker -> customer    'Sends order notifications'   'email'
```

Nothing is implemented and nothing here pretends otherwise: there is no worker
code, no broker configuration, no deployment manifest, and the record's only
evidence is a `planned` test path. The choice between routing options is argued
in the record (`inline-in-api`, `transactional-outbox`, `worker-with-queue`),
which is why the proposal carries one decision rather than three designs.

```bash
npx --yes likec4@1.60.0 validate                  # Valid (1 files)
npx --yes likec4@1.60.0 export json --skip-layout -o /tmp/head.json
## Recreate /tmp/base.json from the standalone baseline using the recipe above.
python3 ../../.agents/skills/c4spec/scripts/diff.py --base /tmp/base.json --head /tmp/head.json
python3 ../../.agents/skills/c4spec/scripts/check.py --model-json /tmp/head.json \
  --change c4spec/changes/add-notification-worker.json \
  --constraints-file c4spec/constraints.json --repo-root . --phase proposal
```

Expected: diff reports `elements.added: ["shop.broker", "shop.worker"]`,
three added relationships with their titles and technologies, `views.added:
["notifications"]` and `views.modified: ["index", "shop-overview"]` — `index` is
the generated landscape view and moves on any element addition. The proposal
check exits 0 with two `planned_path` warnings; the same record at
`--phase completion` exits 1 with `still_planned` plus `missing_path`, which is
the point: a proposed architecture cannot be reported as delivered.

Review the full `.c4` patch alongside the computed diff. The diff includes
`elements.addedDetails` (kind, name, responsibility, technology) and a caution
for the generated `index` landscape view. This output remains advisory and
does not imply the worker or broker is running.
