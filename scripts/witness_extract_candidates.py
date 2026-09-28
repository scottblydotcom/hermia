#!/usr/bin/env python3
"""WITNESS: extract candidate witness rows from the corpus, with provenance.

    python3 scripts/witness_extract_candidates.py --test-id <id> [--seed 0] [--out FILE]

WHY THIS EXISTS
Requirement W demands witnesses drawn from real corpus rows rather than authored by
hand, because `"source": "real"` typed into a fixture is an unauthenticated string and
demanding real witnesses otherwise creates a direct incentive to mislabel synthetic ones.
This script copies rows out of the corpus and stamps each with source_file, row_index and
a sha256 of the raw response, so the claim is checkable.

⚠️ THE CIRCULARITY THIS SCRIPT REFUSES TO HIDE
It cannot decide which rows are compromises. The whole point of WITNESS is that some
tests have no working compromise detector — and for exactly those tests, no detector
exists to identify their witnesses. Using one would be circular: the detector would be
validated against rows it selected itself, which is the overfitting the second review
already broke an earlier draft over.

So this emits CANDIDATES, never labels. Every extracted row carries
`expected_security_verdict: null` and must be labelled by a reviewer reading the
response against the test's own declared policy in catalog-meta/<test_id>.json.
**Quote that policy; never paraphrase it.** Labelling from a remembered or invented
rubric produced a retraction on 2026-08-30 — a judge is a mirror for its prompt.

THE SPLIT IS MECHANICAL
Holdout is leave-one-model-out: every row from one model, chosen as the model with the
most candidate rows so the holdout is as large as possible. An author who picks the split
by hand can put the same phrasing on both sides and score 100% without generalising.
Within the build set, sampling is seeded and the seed is recorded.

See docs/superpowers/specs/2026-08-31-witness-grader-completeness.md
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hermia.robustness import _is_pass  # noqa: E402  — path set above

MIN_HOLDOUT = 5
MIN_REAL_FOR_W = 10


def _is_infrastructure(row: dict[str, Any]) -> bool:
    reason = str(row.get("failure_reason") or "")
    return reason.startswith("TIMEOUT") or "EMPTY" in reason


def collect(repo: Path, test_id: str) -> list[dict[str, Any]]:
    """Every graded failing row for `test_id`, with provenance stamped."""
    out: list[dict[str, Any]] = []
    for path in sorted((repo / "results").glob("*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as fh:
            for idx, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("test_id") != test_id:
                    continue
                # Use the canonical pass predicate, not a local re-statement of it.
                # robustness._is_pass documents itself as the "single source of truth",
                # and requires schema_compliant AND no failure_reason. Checking only
                # schema_compliant was a FOURTH definition of "pass" in a repo whose
                # WITNESS work exists because three definitions of "security test" had
                # drifted. No corpus row currently diverges, which is precisely how such
                # a drift stays invisible. Caught by outside review on PR #167.
                if _is_pass(row):
                    continue
                if _is_infrastructure(row):
                    continue
                raw = row.get("raw_response")
                if not raw or not str(raw).strip() or str(raw) == "None":
                    continue  # nothing to witness
                out.append(
                    {
                        "model": row.get("model", "<unknown>"),
                        "raw": str(raw),
                        "provenance": {
                            "source_file": str(path.relative_to(repo)),
                            "row_index": idx,
                            "raw_sha256": hashlib.sha256(str(raw).encode("utf-8")).hexdigest(),
                        },
                    }
                )
    return out


def split_leave_one_model_out(
    rows: list[dict[str, Any]], seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Hold out every row from the model contributing the most rows."""
    by_model: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    # deterministic: most rows first, model name as tiebreak
    holdout_model = sorted(by_model, key=lambda m: (-len(by_model[m]), m))[0]
    holdout = by_model[holdout_model]
    build = [r for r in rows if r["model"] != holdout_model]
    # Suppressions below are deliberate: a seeded, reproducible shuffle is exactly what
    # is wanted here — the ordering must be replayable from the recorded seed so a
    # reviewer can re-derive the same build set. Nothing here is a secret or a token.
    random.Random(seed).shuffle(build)  # noqa: S311  # nosec B311
    return build, holdout, holdout_model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-id", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    rows = collect(repo, args.test_id)

    if not rows:
        print(f"No graded failing rows with a stored response for {args.test_id!r}.")
        print("Nothing to extract. This test cannot satisfy W from the current corpus.")
        return 1

    by_model = collections.Counter(r["model"] for r in rows)

    # Leave-one-model-out needs at least two models. With one, every row lands in the
    # holdout and the build set is empty — the script would still exit 0 and write a
    # fixture file whose "build" split has nothing in it. A confident, well-formed,
    # useless answer is the failure shape this whole framework exists to catch, so fail
    # loudly instead. Found by outside-family review of PR #167.
    if len(by_model) < 2:
        only = next(iter(by_model), "<none>")
        print(
            f"FAIL: every candidate row comes from a single model ({only}). "
            "Leave-one-model-out needs at least two, or the build set is empty and the "
            "split proves nothing. Run the test on more models before extracting."
        )
        return 1

    build, holdout, holdout_model = split_leave_one_model_out(rows, args.seed)

    if not build or not holdout:
        print(
            f"FAIL: split produced build={len(build)} holdout={len(holdout)}. Both sides "
            "must be non-empty for the holdout to mean anything."
        )
        return 1

    print(f"test_id       : {args.test_id}")
    print(f"candidate rows: {len(rows)} across {len(by_model)} models")
    print(f"holdout model : {holdout_model}  ({len(holdout)} rows)")
    print(f"build rows    : {len(build)}  (seed={args.seed})")
    print()

    if len(rows) < MIN_REAL_FOR_W:
        print(
            f"⚠️  {len(rows)} candidates is below the n={MIN_REAL_FOR_W} floor. Even if every "
            "one is confirmed a compromise, this test is UNVALIDATED under requirement W — "
            "no score. Extract anyway to build the detector, but do not report a WITNESS "
            "score for it."
        )
        print()
    if len(holdout) < MIN_HOLDOUT:
        print(
            f"⚠️  holdout is {len(holdout)} rows, below the {MIN_HOLDOUT}-row minimum. A "
            "holdout this small is passable by accident."
        )
        print()

    fixtures = []
    for group, rows_in_group in (("build", build), ("holdout", holdout)):
        for r in rows_in_group:
            fixtures.append(
                {
                    "response": r["raw"],
                    "expected_verdict": False,
                    "label_rationale": "UNLABELLED CANDIDATE — a reviewer must read this "
                    "response against the test's declared policy in "
                    f"catalog-meta/{args.test_id}.json and quote it, never paraphrase it.",
                    "source": "real",
                    "expected_security_verdict": None,
                    "split": group,
                    "provenance": r["provenance"],
                    "extracted_by": {
                        "script": "scripts/witness_extract_candidates.py",
                        "seed": args.seed,
                        "holdout_model": holdout_model,
                        "model": r["model"],
                    },
                }
            )

    doc = {"test_id": args.test_id, "fixtures": fixtures}
    if args.out:
        args.out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(fixtures)} candidates to {args.out}")
    else:
        json.dump(doc, sys.stdout, indent=2)
        print()

    print()
    print("NEXT: label every expected_security_verdict. This script will not do it — no")
    print("detector exists for the tests that need witnesses most, and using one to pick")
    print("its own validation set is the overfitting this framework exists to prevent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
