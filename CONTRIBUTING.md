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

## Security checks

Dependabot checks npm, Python, and GitHub Actions weekly. Minor and patch
updates are grouped where possible. LikeC4, Skills CLI, and major updates
get individual review. Regular updates have a seven-day cooldown.
Dependabot security updates run separately. The maintainer reviews and merges
dependency PRs.

GitHub's Dependency Review checks the dependency diff of every PR and fails on
new high or critical vulnerabilities. Review applicable license notices when
adding a dependency. CodeQL scans JavaScript/TypeScript, Python, and Actions on
PRs, pushes to `main`, and weekly. The `Workflow security` CI job runs zizmor.
OpenSSF Scorecard evaluates `main` and publishes its results to code scanning
and the Scorecard dashboard. [Public results](https://scorecard.dev/viewer/?uri=github.com/slowickip/c4spec)

Run actionlint and zizmor from the repository root.

```bash
actionlint -ignore 'unexpected key "cache-mode"'
zizmor --offline --collect all --strict-collection .github
```

The actionlint exclusion accommodates releases that predate GitHub's
`cache-mode` key. The zizmor exception in CI allows a clean consumer install
from the npm tarball being tested.

Triage alerts in GitHub Security. Check which releases and workflows are
affected, update dependencies or code through a PR, and record the reason
for any dismissal. Coordinate unpublished vulnerability fixes through the
private advisory process. [GitHub Security](https://github.com/slowickip/c4spec/security) · [Reporting instructions](SECURITY.md)

## Releases

Versioning and npm releases use [Changesets](.changeset/README.md) in `alpha`
prerelease mode ([pre state](.changeset/pre.json)) and
[the release workflow](.github/workflows/release.yml):

1. Add a changeset on feature branches when user-facing behavior changes:
   `npm run changeset`.
2. Merging to `main` runs the `version` job in `.github/workflows/release.yml`,
   which opens or updates the `chore(release): version packages` pull request
   (updating `package.json`, `package-lock.json`, and `CHANGELOG.md`).
3. While `NPM_RELEASE_ENABLED` is unset or not `'true'`, merging the version PR
   skips npm publication.
4. Once `NPM_RELEASE_ENABLED` is set to `'true'` in repository variables, merging
   a version PR starts publication after functional CI and zizmor succeed on
   the merged commit. Changesets checks the tarball, publishes with npm Trusted
   Publishing and provenance, tags `v<version>`, and reconciles the GitHub
   Release. The workflow attaches a CycloneDX runtime SBOM to the release for
   the exact commit recorded by npm. The manual bootstrap release used
   `latest`. Subsequent Changesets prereleases use `alpha`.
5. Run `npm run changeset -- pre exit` when graduating from alpha prereleases to
   stable releases.

Publish from the owner-controlled `main` branch. The npm Trusted Publisher for
`@slowickip/c4spec` uses owner `slowickip`, repository `c4spec`, and workflow
`release.yml`. If the publisher needs inspection or repair, sign in on npmjs.com
with package maintainer access. The workflow uses GitHub OIDC for npm and the
built-in GitHub token for release PRs, tags, and assets. Verify an example
attestation with `npm view @slowickip/c4spec@0.1.0-alpha.4 dist.attestations`.

GitHub's `main-merge-access` ruleset grants merge access to the owner. The
separate `main-quality` ruleset requires successful functional CI, Dependency
Review, and zizmor checks. It also requires CodeQL results and resolved review
conversations. Changesets can open version PRs with the
built-in token. If GitHub pauses a bot-created PR's checks for approval,
approve the workflow runs from the PR Checks tab before merging.

## Pull requests

Include reproducible test commands and outcomes. For an architecture change,
review the LikeC4 patch and generated diagrams. Use the pinned compiler and
model stable architectural boundaries and relationships. Preserve applicable
third-party attribution when importing code or text. [C4 guidance](docs/c4-governance.md) · [Third-party notices](docs/upstream-reuse.md)
