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
)

_INSERT_SQL = (
    f"INSERT INTO hermia_results ({', '.join(_PG_COLUMNS)}) "
    f"VALUES ({', '.join(f'%({c})s' for c in _PG_COLUMNS)}) "
    "ON CONFLICT (run_id, host, model, test_id) DO NOTHING"
)

_REQUIRED_FIELDS = {"run_id", "host", "model", "test_id"}


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

    if dry_run:
        print(f"[dry-run] Would process {len(valid_rows)} row(s)")
        for r in valid_rows:
            print(
                f"  run_id={r.get('run_id')}  host={r.get('host')}"
                f"  model={r.get('model')}  test_id={r.get('test_id')}"
            )
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
                records = [{c: row.get(c) for c in _PG_COLUMNS} for row in valid_rows]
                if records:
                    execute_batch(cur, _INSERT_SQL, records)
        print(f"Processed {len(records)} row(s) (duplicates skipped via ON CONFLICT)")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Push hermia eval results to Postgres")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("HERMIA_PG_DSN", ""),
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
    args = parser.parse_args()

    if not args.dry_run and not args.dsn:
        sys.exit("--dsn or HERMIA_PG_DSN is required")

    if not args.results_dir.is_dir():
        sys.exit(f"Results directory not found: {args.results_dir}")

    rows = collect_results(args.results_dir)
    if not rows:
        print("No results found.")
        return

    push(rows, args.dsn, args.dry_run)
