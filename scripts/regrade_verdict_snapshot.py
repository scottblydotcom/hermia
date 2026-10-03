#!/usr/bin/env python3
"""Snapshot every security row's verdict under the INSTALLED grader, or diff two snapshots.

A grader change must be shown to move exactly the rows it claims to move. Run this once
with the base code importable and once with the branch, then diff:

    python3 scripts/regrade_verdict_snapshot.py --out base.json   # on dev
    python3 scripts/regrade_verdict_snapshot.py --out head.json   # on the branch
    python3 scripts/regrade_verdict_snapshot.py --diff base.json head.json

Each snapshot records WHICH hermia it imported (module path and git sha). Comparing a
change to itself is the failure this guards against: always check the two headers differ.

The default corpus is the canonical population, the top-level `results/*.jsonl`. Its
subdirectories hold backups and superseded copies; globbing them in would double-count rows.

Rows are keyed by the sha256 of their exact line bytes plus an occurrence index, so the
key does not depend on any field the grader might change. Rows are never copied out; the
snapshot holds keys, test ids and verdicts only.

Exit 0 = snapshot written, or a usable diff printed. Exit 2 = the diff proves nothing (same
grader, unidentified or uncommitted grader source, or different row sets). Exit 1 = bad input.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Grade THIS checkout's code, not whatever `hermia` the interpreter has installed. An editable
# install points at one worktree; a site-packages install at none. Either would make two runs from
# two checkouts grade the same code, which the identity check in `diff` would then flag as unusable.
_SRC = Path(__file__).resolve().parents[1] / "src"
if (_SRC / "hermia").is_dir():
    sys.path.insert(0, str(_SRC))


def _grader_identity() -> dict[str, str]:
    import hermia

    src = Path(hermia.__file__).resolve().parent
    try:
        sha = subprocess.run(
            ["git", "-C", str(src), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(src), "status", "--porcelain", "--", "."],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sha, dirty = "unknown", ""
    return {"module": str(src), "git_sha": sha, "src_dirty": "yes" if dirty else "no"}


def snapshot(pattern: str) -> dict[str, Any]:
    from hermia.regrade import regrade_row
    from hermia.schemas import SECURITY_TEST_IDS

    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise SystemExit(f"no files match {pattern!r}")
    verdicts: dict[str, list[str]] = {}
    seen: Counter[str] = Counter()
    unreadable = 0
    for path in files:
        with open(path, "rb") as fh:
            for raw_line in fh:
                try:
                    row = json.loads(raw_line)
                except ValueError:
                    unreadable += 1
                    continue
                if not isinstance(row, dict) or row.get("test_id") not in SECURITY_TEST_IDS:
                    continue
                digest = hashlib.sha256(raw_line).hexdigest()
                key = f"{digest}:{seen[digest]}"
                seen[digest] += 1
                record = regrade_row(row)
                verdict = record["security_verdict"] if record else "ungradeable"
                verdicts[key] = [row["test_id"], verdict]
    counts = Counter(v for _, v in verdicts.values())
    return {
        "grader": _grader_identity(),
        "corpus": {"pattern": pattern, "files": len(files), "unreadable_lines": unreadable},
        "rows": len(verdicts),
        "counts": dict(sorted(counts.items())),
        "verdicts": verdicts,
    }


def diff(a_path: str, b_path: str) -> int:
    """Print the verdict moves from A to B. Returns 2 when the comparison proves nothing."""
    a = json.loads(Path(a_path).read_text())
    b = json.loads(Path(b_path).read_text())
    print("A:", a["grader"], a["rows"], "rows", a["counts"])
    print("B:", b["grader"], b["rows"], "rows", b["counts"])
    unusable = []
    # Compare commits, not the whole identity: two clean checkouts of ONE commit differ only in
    # their module path, and they still grade with the same code (CodeRabbit, PR #211).
    if a["grader"]["git_sha"] == b["grader"]["git_sha"]:
        unusable.append("both snapshots graded the same commit")
    if "unknown" in (a["grader"]["git_sha"], b["grader"]["git_sha"]):
        unusable.append("a snapshot could not identify its grader's commit")
    if "yes" in (a["grader"]["src_dirty"], b["grader"]["src_dirty"]):
        unusable.append("a snapshot was graded from uncommitted source")
    av, bv = a["verdicts"], b["verdicts"]
    only_a, only_b = set(av) - set(bv), set(bv) - set(av)
    if only_a or only_b:
        unusable.append(f"row sets differ ({len(only_a)} only in A, {len(only_b)} only in B)")
    moves = Counter(
        (av[k][0], av[k][1], bv[k][1]) for k in set(av) & set(bv) if av[k][1] != bv[k][1]
    )
    # UNUSABLE goes first: a reader who stops at the move count must not see a bare "0".
    for reason in unusable:
        print(f"UNUSABLE: {reason}; this diff proves nothing.")
    label = "verdict moves (UNUSABLE)" if unusable else "verdict moves"
    print(f"{label}: {sum(moves.values())}")
    for (test_id, before, after), n in sorted(moves.items()):
        print(f"  {n:5d}  {test_id}: {before} -> {after}")
    return 2 if unusable else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default="results/*.jsonl", help="glob of result jsonl files")
    ap.add_argument("--out", help="write a snapshot to this path")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"), help="diff two snapshots")
    args = ap.parse_args(argv)
    if args.diff:
        return diff(*args.diff)
    if not args.out:
        ap.error("--out or --diff is required")
    snap = snapshot(args.corpus)
    Path(args.out).write_text(json.dumps(snap))
    print(snap["grader"], snap["rows"], "rows", snap["counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
