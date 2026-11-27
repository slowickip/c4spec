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
packets, outside of commits. Use `npm pack` to check the tarball.

## Pull requests

Include reproducible test commands and outcomes. For an architecture change,
review the LikeC4 patch and generated diagrams. Use the pinned compiler and
model stable architectural boundaries and relationships. Preserve applicable
third-party attribution when importing code or text. [C4 guidance](docs/c4-governance.md) · [Third-party notices](docs/upstream-reuse.md)
