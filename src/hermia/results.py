"""Persist evaluation results to timestamped JSON and CSV files."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def save_results(
    results: list[dict[str, Any]], results_dir: Path
) -> tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir.mkdir(parents=True, exist_ok=True)
    json_out = results_dir / f"eval_{ts}.json"
    csv_out = results_dir / f"eval_{ts}.csv"

    with open(json_out, "w") as f:
        json.dump(results, f, indent=2)

    if results:
        with open(csv_out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    return json_out, csv_out
