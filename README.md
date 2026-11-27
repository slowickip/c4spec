# C4Spec

**C4Spec helps people and agents maintain and review C4 architecture in Git.**
Both use cases share a versioned **LikeC4 model**, portable modeling guidance
and visual comparison.

- **Diagram maintenance.** Ask an agent to review or update current-state
  diagrams on demand. Use it alongside OpenSpec or your existing development
  workflow.
- **Model-first development (experimental).** Opt into C4Spec's extended
  phase skills to propose, review, apply and verify changes with LikeC4 as the
  architectural specification.

**Alpha preview (`0.1.0-alpha.3`).** The CLI supports single-repository
projects using Git, bundled LikeC4 **1.61.0**, and Node.js **22.23.3 or
later in the 22.x line**, **24.x**, or **26.x**. Install from a release
tarball or build from a reviewed source snapshot.

## Install and try the CLI

To try the CLI from a release tarball, install it into a scratch directory.

```bash
c4spec_install="$(mktemp -d)"
npm install --omit=dev --prefix "$c4spec_install" ./slowickip-c4spec-0.1.0-alpha.3.tgz
"$c4spec_install/node_modules/.bin/c4spec" version
```

Or install the tarball into a project's `devDependencies` (`npm install --save-dev ./slowickip-c4spec-0.1.0-alpha.3.tgz` and run `npx c4spec version`).

From a reviewed C4Spec source checkout or source archive:

```bash
npm ci
npm run build
node bin/c4spec.js version
```

The build compiles the TypeScript CLI to JavaScript. After building, you can
run `node bin/c4spec.js --help` directly from the checkout, or run `npm pack`
to build a distributable `.tgz` tarball.
From a project directory, choose the skills for your agent (substitute
`node /path/to/c4spec/bin/c4spec.js` or `$c4spec_install/node_modules/.bin/c4spec`
for `c4spec` if not on `PATH`):

```bash
c4spec init --agent codex                     # basic profile, the default
c4spec init --agent codex --profile extended  # add the model-first workflow
```

The **basic** profile installs `c4spec` and `c4spec-maintain`. The
**extended** profile includes those two skills and all seven workflow skills.
You can run the extended command later with the same agent selection to add
the workflow skills and keep existing skill files. Add `--dry-run` to see the
selected profile and skills to install. Use `--model-dir` for a custom model
location. The CLI runs without Python.

| Command | Purpose |
| --- | --- |
| `c4spec init [directory]` | Create a starter model if needed and install a skill profile with `--agent` |
| `c4spec doctor` | Check tool versions, installed skill revisions and model discovery |
| `c4spec update --dry-run` | Preview skill file changes against the running CLI's bundle |
| `c4spec validate` | Compile and lint the model and any supplied C4Spec records |
| `c4spec diff --base origin/main` | Show Git-scoped source and computed delta |
| `c4spec review --base origin/main --out /tmp/c4spec-review` | Bundle a LikeC4 viewer and review evidence for the committed model |
| `c4spec version` | Show the C4Spec, LikeC4 and Node versions |

Use `--json` for machine-readable output. See the
[consumer guide](docs/consumer-guide.md) for setup and verification commands.

## Maintain diagrams alongside your existing workflow

With the basic profile installed, ask your agent, “Use `c4spec-maintain` to
update the container diagram for the queue migration already implemented on
this branch.” The agent checks the repo evidence, edits the relevant LikeC4
model or views directly, and validates
them using your compiler pin. For an audit, ask it to review the diagrams and
report findings. Keep using OpenSpec for proposals and implementation.

The reference GitHub workflow renders visual diffs for both use cases.
Fork pull requests get downloadable PNGs. Pull requests from branches in the
same repository also get an inline comment. [Workflow setup](docs/consumer-guide.md#github-pr-diagram-review)

## Try model-first development

With the CLI installed and a Git author configured, create a scratch project
and commit the starter architecture:

```bash
demo="$(mktemp -d)"
c4spec init "$demo/project" --agent codex --profile extended
cd "$demo/project"
git init -b main
git add architecture
git commit -m "Add the starter model"
git switch -c notifications
```

Propose an integration with an external notification service in the same model:

```bash
cat >> architecture/model.c4 <<'LIKEC4'

diff notifications 'Send notifications' {
  add {
    notifier = system 'Notification service' {
      description 'Delivers messages to application users.'
    }
    app -> notifier 'Sends notification requests' 'HTTPS'
  }
}
LIKEC4

c4spec validate
git add architecture/model.c4
git commit -m "Propose the notification integration"
c4spec diff --base main
c4spec review --base main --diff notifications --out "$demo/review"
c4spec review --check-proposal "$demo/review/review.json"
```

Open the generated `review-site/index.html`. Choose **Application context**,
then **Send notifications** in the model state menu. Compare **As-is**,
**Changes** and **To-be**. The review packet contains the Git source patch and
the expected applied model. C4Spec rehearses the application in scratch.

To finish the scratch exercise, apply and verify the proposal:

```bash
npm exec --yes --package=likec4@1.61.0 -- likec4 diff apply notifications architecture
git add architecture/model.c4
git commit -m "Apply the notification integration"
c4spec validate
c4spec review --check-applied "$demo/review/review.json"
```

The consumer guide covers review and validation of model and code changes
together. [Consumer guide](docs/consumer-guide.md)

## C4 levels: L1, L2 and L3

C4Spec uses the standard C4 **zoom levels**, not three phases of specification work:

| Level | Question to answer | Typical scope |
| --- | --- | --- |
| **L1 — System Context** | Who uses the system, and which external systems connect to it? | One software system, people and neighboring systems |
| **L2 — Container** | What major applications and data stores make up this system? | APIs, workers, databases and brokers, with relationships |
| **L3 — Component** | What significant internal parts make up one selected container? | Logical components and responsibilities *inside* one application |

L4 (code-level detail) is optional. **You don't have to model every level**: start with context and containers, and add components only when the extra detail helps a review. A C4 *container* is a running application or data store, **not necessarily a Docker container**. **For structural views, put `L1 —`, `L2 —`, or `L3 —` at the start of the visible LikeC4 `title`**, so it appears directly in the diagram and navigation. Keep the `view` ID stable and don't mislabel focused, dynamic or deployment views. See the [canonical modeling guidance](.agents/skills/c4spec/references/c4-governance.md) (and [docs/c4-governance.md](docs/c4-governance.md)); a worked level mapping is in `examples/mini-project/README.md` in a source checkout or archive.

## Model-first workflow

The model-first phase skills are **experimental** and installed via `--profile extended`.
For repositories pinned to **LikeC4 1.61.0**, propose an architecture change
as a named **native `diff` in the existing `.c4` source on a Git branch**.
The current model remains **As-is**; the LikeC4 viewer shows **As-is /
Changes (red removals, green additions) / To-be**. There is **no mandatory
per-change JSON file** and no second architecture model.

**Supported change types matter.** Native 1.61 diffs support adding/removing
elements and relationships, and extending tags/links/metadata. Existing
element title/description/technology edits and view changes use ordinary Git
source edits plus computed/source review, even on 1.61. Preserve element
identity; do not delete/recreate a node just to obtain red/green colors.
Validate first: `diff list` alone can exit successfully for invalid syntax.

1. **`c4spec-explore`** (optional): understand the request, current model,
   alternatives and evidence.
2. **`c4spec-propose`**: add a native `diff NAME` for genuine architectural
   changes; for behavior/config-only work, leave `.c4` untouched. Run
   `likec4 validate`, `likec4 diff list` and `likec4 diff apply NAME --dry-run`.
3. **`c4spec-review`**: review the exact Git SHA, raw patch and the native
   As-is/Changes/To-be visualization. Resolve overlaps and decide whether
   to authorize implementation. A plain Mermaid preview is *not* the native
   interactive before/after comparison.
4. **`c4spec-apply`**: after explicit authorization, implement authoritative
   code/config/tests, preview and then run `likec4 diff apply NAME` on the
   feature branch. The diff declaration disappears; the canonical model
   becomes To-be.
5. **`c4spec-verify`** runs actual tests and confirms the applied model
   matches what was reviewed. **`c4spec-finish`** prepares a human-reviewed
   PR and merge. **`c4spec-continue`** resumes from Git and any pending diffs.

For a concrete **replace-one-node** example from a source checkout or archive,
follow the instructions in `prototype/native-diff-first/README.md`. The
fixture uses Python and checks preview, apply, invalid syntax and overlapping
removals with the pinned compiler.

For a committed proposal, `c4spec review` reads the exact Git sources, builds
the native LikeC4 viewer and records the expected applied sources from a scratch
copy. Its check modes verify that the committed proposal and applied model still
match the packet.
Start with the [consumer guide](docs/consumer-guide.md), which covers installation,
native changes, direct property/view edits and behavioral verification.

**Compatibility:** Existing projects on 1.60.0 cannot parse native diff
blocks; keep their direct-branch-edit and optional advisory `diff.py`
flow until individually upgraded and verified. The optional structured
change JSON remains only for otherwise-unrepresented non-topological
requirements; use existing tests/contracts and PRs whenever sufficient.

The phase skills guide the review and implementation decisions. You can
revisit phases, with the C4 elements and relationships defined in LikeC4.

## Install skills separately

For skills-only installs, use [skills.sh](https://skills.sh/) from the consumer
and pass the absolute path to the reviewed C4Spec checkout:

```bash
npx --yes skills@1.8.1 add /path/to/c4spec --skill c4spec c4spec-maintain -a codex -y
```

Use `--skill '*'` for the extended set. Pin the source to a reviewed commit
and check the installed skill directory and
`skills-lock.json`. The shared C4Spec skill includes its maintained
[LikeC4 DSL/CLI guidance](.agents/skills/c4spec/references/likec4/README.md).
**Validated compiler: exactly 1.61.0**; newer releases require compatibility
validation and any necessary skill/script adjustments before adoption.
No separate upstream skill is required.

Single-agent installation may place skills directly under `.claude/skills/`,
not `.agents/skills/`. **C4Spec checks, schemas and governance references live
inside its shared `c4spec` skill**, so both modes work.
See [skill distribution](docs/skill-distribution.md) for tested conventions.

Optional offline fallback from a source checkout or archive, without Node or network access:

```bash
python3 scripts/install.py --target /path/to/your-project --dry-run
python3 scripts/install.py --target /path/to/your-project --tools auto
```

The fallback preserves existing skills unless `--force` is explicitly used.
For schema checks, install Python 3.10+ and `jsonschema` via
`pip install -r <installed-c4spec-skill>/requirements.txt`.
Pin a published LikeC4 release independently. The canonical `.c4` model
still lives in the consuming project's repository.

## Legacy scripts and teaching fixtures

- `examples/mini-project/README.md` (in a source checkout or archive) — teaching project with independently compiled test baselines.
- `python3 <installed-c4spec-skill>/scripts/check.py --model-json <export.json> --change <change.json> --repo-root <project> --phase proposal`
- `python3 <installed-c4spec-skill>/scripts/check.py --model-json <export.json> --change <change.json> --repo-root <project> --phase completion`
- `python3 <installed-c4spec-skill>/scripts/diff.py --base <base-export.json> --head <head-export.json>`
- `python3 <installed-c4spec-skill>/scripts/provenance.py --model-dir <architecture-dir> --export <abs export.json> --git-commit <40-hex> --compiler-version <pinned LikeC4> --out <provenance.json>`
- `python3 <installed-c4spec-skill>/scripts/diff.py --base <b.json> --head <h.json> --base-provenance <b-prov.json> --head-provenance <h-prov.json> --repo-root <project>`
- `python3 <installed-c4spec-skill>/scripts/render_review.py --diff <diff.json> [--check <check.json>] [--change <change.json>] --render <view-id>=<native.png> --html <scratch>/review.html [--markdown <scratch>/review.md]`

First run `likec4 validate`; obtain export JSON with the pinned LikeC4
version. The diff helper compares a conservative *subset* of computed-model
semantics, reports modified field values, and hashes normalized before/after model snapshots; it does **not** prove implementation conformance, preserve all view
selector semantics, or replace Git's raw C4 source diff. No silent automatic
updates from implementation are permitted.

Published LikeC4 **1.61.0** now supports named `diff` blocks, native
As-is/Changes/To-be review and `diff apply`: [official model diff docs](https://likec4.dev/dsl/diff/).
Use the legacy `diff.py` helper for advisory source comparison and projects
pinned to 1.60.0.

## Repository boundary

In a source checkout or archive, C4Spec manages its own architecture model in
`architecture/c4spec.c4`. From a built source checkout, run
`node bin/c4spec.js validate --model-dir architecture` or open the diagrams
with `npm exec -- likec4 start architecture`. Contributor instructions
are in [CONTRIBUTING.md](CONTRIBUTING.md); see [SECURITY.md](SECURITY.md) for
vulnerability reporting and [CHANGELOG.md](CHANGELOG.md) for release notes.

Each consuming repository owns its C4 model, tests and configuration. Its code
and contracts govern behavior. The human reviewer decides whether to approve
and merge a change.

C4Spec follows the C4 model.
[The C4 model](https://c4model.com/) · [Diagram review checklist](https://c4model.com/diagrams/checklist)

## License

C4Spec's original work and phase skills use Apache 2.0. Bundled LikeC4
guidance and upstream skill hashing code carry their MIT notices.
[Apache 2.0 license](LICENSE) · [Notice](NOTICE) ·
[Upstream reuse](docs/upstream-reuse.md) · [Upstream licenses](licenses/)
