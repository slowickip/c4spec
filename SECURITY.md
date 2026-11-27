# Security policy

Use GitHub’s **Report a vulnerability** button to contact the maintainers
privately. Include the affected version, the smallest example that reproduces
the issue, and its impact. Keep vulnerability details and credentials out of
public issues and PRs. [Report a vulnerability](https://github.com/slowickip/c4spec/security/advisories/new)

Security fixes target the latest alpha release. The contributing guide
describes automated checks and how maintainers handle alerts.
[Security checks](CONTRIBUTING.md#security-checks)

The default GitHub diagram workflow renders pull request content in a job
with read-only repository
permissions. A separate job publishes comments for same-repository pull
requests. Running the CLI locally can load the project’s LikeC4 configuration,
so use it with repositories you trust. [Reference workflow](.github/workflows/pr-model-diff.yml)
