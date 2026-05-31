#!/usr/bin/env python3
"""Analyze a hermia JSONL result file for VRAM spill and throughput.

Usage: python3 scripts/analyze_spill.py results/eval_YYYYMMDD_HHMMSS.jsonl
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

MIN_ACCEPTABLE_TPS = 5.0  # below this = delete
BORDERLINE_TPS = 9.0      # below this = flag for review


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def analyze(rows: list[dict]) -> None:
    # Group by (fleet_host_name, model)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        host = r.get("fleet_host_name") or r.get("host", "unknown")
        model = r.get("model", "unknown")
        groups[(host, model)].append(r)

    print(f"\n{'HOST':<30} {'MODEL':<45} {'PASS%':>6} {'MED t/s':>8} {'VRAM GB':>8} {'VERDICT'}")
    print("-" * 115)

    for (host, model), group in sorted(groups.items()):
        passed = sum(1 for r in group if r.get("schema_compliant"))
        total = len(group)
        pass_pct = 100.0 * passed / total if total else 0

        tps_vals = [r["tokens_per_sec"] for r in group if r.get("tokens_per_sec") is not None]
        med_tps = sorted(tps_vals)[len(tps_vals) // 2] if tps_vals else 0.0

        vram_vals = [r["vram_server_gb"] for r in group if r.get("vram_server_gb") is not None]
        avg_vram = sum(vram_vals) / len(vram_vals) if vram_vals else 0.0

        if not vram_vals:
            verdict = "REVIEW  — unknown VRAM"
        elif avg_vram == 0.0:
            verdict = "DELETE — CPU fallback (vram=0)"
        elif med_tps < MIN_ACCEPTABLE_TPS:
            verdict = f"DELETE — t/s {med_tps:.1f} below {MIN_ACCEPTABLE_TPS}"
        elif med_tps < BORDERLINE_TPS:
            verdict = f"REVIEW  — borderline t/s {med_tps:.1f}"
        else:
            verdict = "KEEP    — acceptable spill"

        print(f"{host:<30} {model:<45} {pass_pct:>5.1f}% {med_tps:>8.1f} {avg_vram:>8.2f}  {verdict}")

    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/analyze_spill.py <results.jsonl>", file=sys.stderr)
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    rows = load_rows(path)
    analyze(rows)
