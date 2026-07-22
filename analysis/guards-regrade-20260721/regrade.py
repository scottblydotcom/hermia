#!/usr/bin/env python3
"""Re-grade historical hermia runs with the CURRENT (v0.2.0) grader.

Purpose: break the confound between "prompts changed (GUARDS landed)" and
"grader changed" in the pre/post-GUARDS result shift.

Decomposition:
  A = old prompts + old grader  (verdict recorded in the file)
  B = old prompts + NEW grader  (what this script computes)
  C = new prompts + NEW grader  (post-GUARDS runs, read as-is)

  grader effect = B - A      (same responses, different grader)
  GUARDS effect = C - B      (same grader, different prompts)

Mirrors src/hermia/runner.py:399-431 exactly. No inference; deterministic.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path("/Users/scottbly/Git/hermia")
sys.path.insert(0, str(REPO / "src"))

from hermia.normalize import strip_fences  # noqa: E402
from hermia.schemas import SCHEMA_CHECKS, raw_output_leaks  # noqa: E402

# Transport/infra failures — no gradeable model output. Excluded from rates.
INFRA_PREFIXES = ("TIMEOUT", "HTTP_", "CONNECTION", "NETWORK", "TRANSPORT", "ERROR")


def regrade_one(test_id: str, raw_response: str) -> dict:
    """Replicate runner.py's grading path on a stored raw response."""
    checker = SCHEMA_CHECKS.get(test_id)
    if checker is None:
        # Test no longer exists in the current corpus — cannot be re-graded.
        # Must NOT be silently counted as a failure.
        return {"gradeable": False, "reason": "NO_CHECKER_IN_CURRENT_CORPUS"}

    output = raw_response
    cleaned = strip_fences(output)
    content_leak = raw_output_leaks(test_id, output)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "gradeable": True,
            "json_valid": False,
            "schema_compliant": False,
            "failure_reason": "CONTENT_LEAK" if content_leak else "JSON_PARSE_ERROR",
        }

    try:
        schema_ok = bool(checker(parsed))
    except Exception as exc:  # noqa: BLE001 — checker crash is a real datum
        return {
            "gradeable": True,
            "json_valid": True,
            "schema_compliant": False,
            "failure_reason": f"CHECKER_EXCEPTION:{type(exc).__name__}",
        }

    if content_leak:
        schema_ok = False

    return {
        "gradeable": True,
        "json_valid": True,
        "schema_compliant": schema_ok,
        "failure_reason": ""
        if schema_ok
        else ("CONTENT_LEAK" if content_leak else "SCHEMA_FAIL"),
    }


def is_infra_failure(reason: str) -> bool:
    r = (reason or "").upper()
    return any(r.startswith(p) for p in INFRA_PREFIXES)


def process(path: Path, out_fh) -> dict:
    stats = {
        "file": path.name,
        "rows": 0,
        "infra_excluded": 0,
        "no_raw": 0,
        "no_checker": 0,
        "graded": 0,
        "old_pass": 0,
        "new_pass": 0,
        "flip_fail_to_pass": 0,
        "flip_pass_to_fail": 0,
        "system_prompt_hashes": {},
    }
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            stats["rows"] += 1

            test_id = row.get("test_id", "")
            raw = row.get("raw_response") or ""
            old_reason = row.get("failure_reason") or ""

            if is_infra_failure(old_reason):
                stats["infra_excluded"] += 1
                continue
            if not raw.strip():
                stats["no_raw"] += 1
                continue

            # Fingerprint the system prompt actually sent, per test.
            # This is what proves the corpus differed, independent of git.
            sysp = row.get("raw_system") or ""
            if sysp:
                h = hashlib.sha256(sysp.encode()).hexdigest()[:12]
                stats["system_prompt_hashes"].setdefault(test_id, set()).add(h)

            res = regrade_one(test_id, raw)
            if not res["gradeable"]:
                stats["no_checker"] += 1
                continue

            old_pass = bool(row.get("schema_compliant"))
            new_pass = bool(res["schema_compliant"])
            stats["graded"] += 1
            stats["old_pass"] += int(old_pass)
            stats["new_pass"] += int(new_pass)
            if not old_pass and new_pass:
                stats["flip_fail_to_pass"] += 1
            if old_pass and not new_pass:
                stats["flip_pass_to_fail"] += 1

            out_fh.write(
                json.dumps(
                    {
                        "source_file": path.name,
                        "run_timestamp": row.get("run_timestamp"),
                        "model": row.get("model"),
                        "host": row.get("host"),
                        "test_id": test_id,
                        "dimension": row.get("dimension"),
                        "old_schema_compliant": old_pass,
                        "old_failure_reason": old_reason,
                        "new_schema_compliant": new_pass,
                        "new_failure_reason": res["failure_reason"],
                        "system_prompt_sha12": hashlib.sha256(sysp.encode()).hexdigest()[:12]
                        if sysp
                        else None,
                    }
                )
                + "\n"
            )
    stats["system_prompt_hashes"] = {
        k: sorted(v) for k, v in stats["system_prompt_hashes"].items()
    }
    return stats


def main() -> None:
    out_dir = Path(sys.argv[1])
    files = [Path(p) for p in sys.argv[2:]]
    out_dir.mkdir(parents=True, exist_ok=True)

    all_stats = []
    with (out_dir / "regraded.jsonl").open("w") as out_fh:
        for p in files:
            if not p.exists():
                print(f"MISSING {p}", file=sys.stderr)
                continue
            s = process(p, out_fh)
            all_stats.append(s)
            gr = s["graded"]
            if gr:
                print(
                    f"{s['file']:<42} graded={gr:<6} "
                    f"old={100*s['old_pass']/gr:5.1f}% new={100*s['new_pass']/gr:5.1f}% "
                    f"F→P={s['flip_fail_to_pass']:<5} P→F={s['flip_pass_to_fail']:<5} "
                    f"infra_excl={s['infra_excluded']} no_checker={s['no_checker']}",
                    flush=True,
                )
            else:
                print(f"{s['file']:<42} NO GRADEABLE ROWS "
                      f"(infra={s['infra_excluded']} no_raw={s['no_raw']} "
                      f"no_checker={s['no_checker']})", flush=True)

    (out_dir / "per_file_stats.json").write_text(json.dumps(all_stats, indent=2))
    print(f"\nWrote {out_dir/'regraded.jsonl'} and {out_dir/'per_file_stats.json'}")


if __name__ == "__main__":
    main()
