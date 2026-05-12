"""Push hermia JSONL eval results to Postgres for Grafana dashboards."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from hermia.results import load_jsonl

_PG_COLUMNS = (
    "run_id",
    "run_timestamp",
    "host",
    "model",
    "test_id",
    "dimension",
    "json_valid",
    "schema_compliant",
    "failure_reason",
    "tokens",
    "elapsed_sec",
    "tokens_per_sec",
    "output_preview",
    "peak_cpu_pct",
    "peak_ram_used_gb",
    "peak_gpu_pct",
    "peak_vram_used_gb",
    "framework_owasp",
    "framework_mitre",
    "framework_maestro",
    "framework_nist",
    "score",
    "run_index",
    "is_cold",
    "cold_warm_delta_tps",
    "consistency_pct",
    "pass_count",
    "robustness_n",
    "judge_score",
    "judge_reasoning",
)

_INSERT_SQL = (
    f"INSERT INTO hermia_results ({', '.join(_PG_COLUMNS)}) "  # nosec B608 — columns from hardcoded tuple; values use psycopg2 %(name)s params
    f"VALUES ({', '.join(f'%({c})s' for c in _PG_COLUMNS)}) "
    "ON CONFLICT (run_id, host, model, test_id, run_index) DO NOTHING"
)

_REQUIRED_FIELDS = {"run_id", "host", "model", "test_id"}


def compute_score(row: dict[str, object]) -> int:
    """Derive a 0–100 quality score from pass/fail fields.

    100 = json valid + schema compliant
     60 = json valid, schema failed
     25 = response received but not valid JSON
      0 = error / timeout / no response
    """
    if row.get("failure_reason"):
        return 0
    if not row.get("json_valid"):
        return 25
    if not row.get("schema_compliant"):
        return 60
    return 100


def collect_results(results_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for jsonl in sorted(results_dir.glob("eval_*.jsonl")):
        if jsonl.is_file():
            rows.extend(load_jsonl(jsonl))
    return rows


def push(rows: list[dict[str, object]], dsn: str, dry_run: bool) -> None:
    valid_rows = [r for r in rows if all(r.get(f) for f in _REQUIRED_FIELDS)]
    skipped = len(rows) - len(valid_rows)
    if skipped:
        print(f"Skipped {skipped} row(s) missing mandatory fields (likely from older runs).")

    fw_map = {
        "framework_owasp": "owasp_llm_top10_2025",
        "framework_mitre": "mitre_atlas_v5_1",
        "framework_maestro": "csa_maestro",
        "framework_nist": "nist_ai_rmf",
    }
    records = []
    for row in valid_rows:
        rec = {c: row.get(c) for c in _PG_COLUMNS}
        rec["score"] = compute_score(row)
        raw_fw = row.get("frameworks")
        fw: dict[str, object] = raw_fw if isinstance(raw_fw, dict) else {}
        for col, key in fw_map.items():
            rec[col] = fw.get(key, [])
        records.append(rec)

    if dry_run:
        print(f"[dry-run] Would process {len(records)} row(s)")
        for r in records:
            print(
                f"  run_id={r.get('run_id')}  host={r.get('host')}"
                f"  model={r.get('model')}  test_id={r.get('test_id')}"
                f"  score={r.get('score')}"
            )
        return

    if not records:
        return

    try:
        import psycopg2
        from psycopg2.extras import execute_batch
    except ImportError:
        sys.exit("psycopg2-binary is required — install with: pip install 'hermia[grafana]'")

    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        sys.exit(f"Failed to connect to Postgres: {e}")

    try:
        with conn:
            with conn.cursor() as cur:
                execute_batch(cur, _INSERT_SQL, records)
        print(f"Processed {len(records)} row(s) (duplicates skipped via ON CONFLICT)")
    finally:
        conn.close()


def main(
    dsn: str | None = None,
    results_dir: Path | str | None = None,
    dry_run: bool | None = None,
    exit_on_error: bool = True,
) -> int:
    """CLI entry point for hermia-push.

    Returns:
        0 — success
        1 — no results found
        2 — argument/path error
        3 — push failure (missing psycopg2 or connection error)
    """
    # Resolve env var before argparse so tests can inject results_dir+dry_run
    # and skip parse_args() entirely while still exercising env-var DSN logic.
    dsn_explicit = dsn is not None
    if dsn is None:
        dsn = os.environ.get("HERMIA_PG_DSN", "")

    if results_dir is None or dry_run is None:
        parser = argparse.ArgumentParser(
            description="Push hermia eval results to Postgres",
            exit_on_error=exit_on_error,
        )
        parser.add_argument(
            "--dsn",
            default=dsn,
            help="Postgres DSN (or set HERMIA_PG_DSN env var)",
        )
        parser.add_argument(
            "--results-dir",
            type=Path,
            default=Path("results"),
            help="Directory containing eval_*.jsonl files (default: ./results)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print rows that would be inserted without writing to Postgres",
        )
        try:
            args = parser.parse_args()
        except argparse.ArgumentError as e:
            print(f"Argument error: {e}", file=sys.stderr)
            return 2
        except SystemExit as e:
            if exit_on_error:
                raise
            return 0 if e.code == 0 or e.code is None else 2
        if not dsn_explicit:
            dsn = args.dsn
        if results_dir is None:
            results_dir = args.results_dir
        if dry_run is None:
            dry_run = args.dry_run

    results_dir = Path(results_dir)

    if not dry_run and not dsn:
        msg = "--dsn or HERMIA_PG_DSN is required"
        print(msg, file=sys.stderr)
        if exit_on_error:
            sys.exit(2)
        return 2

    if not results_dir.is_dir():
        msg = f"Results directory not found: {results_dir}"
        print(msg, file=sys.stderr)
        if exit_on_error:
            sys.exit(2)
        return 2

    rows = collect_results(results_dir)
    if not rows:
        print("No results found.")
        return 1

    try:
        push(rows, dsn, dry_run)
    except SystemExit as e:
        if e.code == 0 or e.code is None:
            return 0
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
        if exit_on_error:
            sys.exit(3)
        return 3
    except Exception as e:
        print(f"Push failed: {e}", file=sys.stderr)
        if exit_on_error:
            sys.exit(3)
        return 3
    return 0
