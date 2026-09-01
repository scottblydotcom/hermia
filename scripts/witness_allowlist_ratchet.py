#!/usr/bin/env python3
"""WITNESS ratchet: the raw-coverage allowlist may only shrink.

pytest cannot enforce this. The suite runs statelessly against one commit, so a pull
request can add an allowlist entry and relax the assertion in the same diff and stay
green. This compares the allowlist in the working tree against the same constant on a
base ref, and fails when entries have been ADDED.

The allowlist is read by parsing the AST, never by importing or executing the base
revision's test file.

    python3 scripts/witness_allowlist_ratchet.py [--base origin/main]

Exit 0 = allowlist shrank or held. Exit 1 = entries added, or the constant went missing.

See docs/superpowers/specs/2026-08-31-witness-grader-completeness.md
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

CONST = "WITNESS_RAW_COVERAGE_ALLOWLIST"
TARGET = "tests/unit/test_schemas.py"


def extract(source: str, origin: str) -> set[str] | None:
    """Pull the allowlist's string literals out of `source` without executing it.

    Returns None when the constant is absent, which the caller distinguishes: absent on
    the BASE is the bootstrap case (this is the change introducing it); absent on HEAD
    means it was deleted or renamed, which must fail.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - malformed base is a real failure
        raise SystemExit(f"FAIL: could not parse {origin}: {exc}") from exc

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == CONST for t in targets):
            continue
        if node.value is None:
            break
        literals: set[str] = set()
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                literals.add(sub.value)
        return literals

    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main", help="base ref to compare against")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    head_src = (repo / TARGET).read_text(encoding="utf-8")

    try:
        base_src = subprocess.run(
            ["git", "show", f"{args.base}:{TARGET}"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: could not read {TARGET} at {args.base}: {exc.stderr.strip()}")
        print("If the base ref is unavailable the ratchet has NOT run — this is not a pass.")
        return 1

    head = extract(head_src, "working tree")
    base = extract(base_src, args.base)

    if head is None:
        print(f"FAIL: {CONST} is missing from {TARGET} in the working tree.")
        print(
            "The ratchet cannot verify an allowlist that was deleted or renamed. If that "
            "was deliberate, update this script in the same change — do not leave a "
            "ratchet pointing at a constant that no longer exists."
        )
        return 1

    if base is None:
        print(f"BOOTSTRAP: {CONST} does not exist at {args.base}.")
        print(f"This is the change that introduces it, with {len(head)} entr"
              f"{'y' if len(head) == 1 else 'ies'}:")
        for h in sorted(head):
            print(f"  {h}")
        print("Nothing to ratchet against yet. Subsequent changes are compared to this.")
        return 0

    added = sorted(head - base)
    removed = sorted(base - head)

    print(f"base ({args.base}): {len(base)} entr{'y' if len(base) == 1 else 'ies'}")
    print(f"head:              {len(head)} entr{'y' if len(head) == 1 else 'ies'}")
    for r in removed:
        print(f"  removed (good):  {r}")

    if added:
        print()
        print("FAIL: the WITNESS raw-coverage allowlist may only shrink.")
        for a in added:
            print(f"  ADDED: {a}")
        print()
        print(
            "Each entry is a security test on which a compromise cannot be detected. "
            "Adding one widens a declared blind spot. If that is genuinely intended, it "
            "needs an explicit decision recorded on the pull request — not a silent line."
        )
        return 1

    print("OK: allowlist shrank or held.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
