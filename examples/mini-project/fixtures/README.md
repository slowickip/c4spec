# Shop test baselines

These snapshots are test inputs. The example model lives in
[`architecture/shop.c4`](../architecture/shop.c4). The `.fixture` suffix
keeps the baselines outside LikeC4 project discovery.

- `before-notifications.c4.fixture` is the reviewed model before the legacy
  notification proposal. The proposal test compares it to the current example
  and checks the new elements, relations and view.
- `before-behavior-change.c4.fixture` is the earlier behavior-only baseline,
  with its two view titles normalized to the current L2 wording. The test
  checks its exact source and separately compiles the two snapshots to verify
  the expected empty model delta.
