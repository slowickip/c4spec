# Shop test baselines

The tests compile these snapshots separately from the
[current shop model](../architecture/shop.c4). The `.fixture` extension
keeps them outside LikeC4 project discovery.

- `before-notifications.c4.fixture` contains the model before the broker and
  notification worker were proposed. The comparison also shows the new
  relationships and the `notifications` view.
- `before-behavior-change.c4.fixture` contains the same architecture as the
  current shop model. The comparison checks for an empty model diff when
  only application behavior changes.
