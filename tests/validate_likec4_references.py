"""Compile complete project examples from installed C4Spec references.

Fragments without both specification and model blocks remain reference snippets.
This command validates a candidate version; it never changes compatibility claims.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide", type=Path, required=True)
    root = Path(__file__).resolve().parents[1]
    # An explicit version still supports manual candidate-version testing.
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.version:
        cli = ["npx", "--yes", f"likec4@{args.version}"]
        expected = args.version
    else:
        cli = [str(root / "node_modules/.bin/likec4")]
        expected = json.loads((root / "package.json").read_text())["dependencies"]["likec4"]
    observed = subprocess.check_output([*cli, "--version"], text=True, timeout=120).strip()
    if observed != expected:
        raise SystemExit(f"Expected {expected}, got {observed!r}")
    count = 0
    with tempfile.TemporaryDirectory(prefix="c4spec-reference-check-") as scratch:
        for path in sorted(args.guide.glob("*.md")):
            blocks = re.findall(r"```(?:likec4|c4)\n(.*?)\n```", path.read_text(), re.S)
            for number, source in enumerate(blocks, 1):
                if not all(re.search(rf"^{name}\s*\{{", source, re.M)
                           for name in ("specification", "model")):
                    continue
                target = Path(scratch) / f"{path.stem}-{number}"
                target.mkdir()
                (target / "model.c4").write_text(source, encoding="utf-8")
                result = subprocess.run(
                    [*cli, "validate", "--json", "--no-layout", str(target)],
                    capture_output=True, text=True, timeout=120)
                if result.returncode:
                    raise SystemExit(f"{path.name} block {number} failed:\n"
                                     + result.stdout + result.stderr)
                count += 1
                print(f"Validated {path.name} block {number}")
    if not count:
        raise SystemExit("No complete project examples found; check the installed guide path")
    print(f"LikeC4 {observed}: {count} complete reference examples passed")


if __name__ == "__main__":
    main()
