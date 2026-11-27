# Contributing to C4Spec

Open an issue for a bug or a proposal. For diagram bugs, include a small LikeC4
example, the compiler version, and what you expected to see.

## Build and test

Use Git, Python 3.11, and Node.js 22.23.3 or later in the 22.x line, 24.x, or
26.x. From a source checkout, run the CLI and Python checks.

```bash
npm ci
npm test
node bin/c4spec.js validate --model-dir architecture
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r .agents/skills/c4spec/requirements.txt
python -m unittest discover -s tests -v
```

Keep generated output, including the local virtual environment and review
packets, outside of commits. Use `npm pack` or `npm run check:pack-version` to
check the tarball.

## Releases

Versioning and npm releases use [Changesets](.changeset/README.md) and
[the release workflow](.github/workflows/release.yml):

1. Add a changeset on feature branches when user-facing behavior changes:
   `npm run changeset`.
2. Merging to `main` runs `.github/workflows/release.yml`, which opens or updates
   the `chore(release): version packages` pull request (updating `package.json`,
   `package-lock.json`, and `CHANGELOG.md`).
3. Merging that version PR publishes `@slowickip/c4spec` to npm via OIDC Trusted
   Publishing and creates the GitHub release.
4. Maintainers can also trigger a manual `alpha` or `beta` prerelease from
   `main` via `workflow_dispatch` when changesets are pending.

First-time npm bootstrap (required once before OIDC Trusted Publishing can be
enabled on npmjs.com): run `npm publish --access public` for the initial
release, then register owner `slowickip`, repository `c4spec`, and workflow
filename `release.yml` under **Trusted Publisher** in the package settings on
npmjs.com.

## Pull requests

Include reproducible test commands and outcomes. For an architecture change,
review the LikeC4 patch and generated diagrams. Use the pinned compiler and
model stable architectural boundaries and relationships. Preserve applicable
third-party attribution when importing code or text. [C4 guidance](docs/c4-governance.md) · [Third-party notices](docs/upstream-reuse.md)
