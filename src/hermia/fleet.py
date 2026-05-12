"""Headless fleet eval runner — multi-host batch evaluation from YAML config."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def load_fleet_config(path: Path) -> list[dict[str, Any]]:
    """Parse fleet YAML. Returns list of host entries. Raises ValueError on invalid config."""
    with path.open() as f:
        data = yaml.safe_load(f)
    entries = data.get("fleet", []) if isinstance(data, dict) else []
    if not entries:
        raise ValueError("Fleet config must contain at least one entry under 'fleet'")
    for i, entry in enumerate(entries):
        if not entry.get("name"):
            raise ValueError(f"Fleet entry [{i}] missing 'name'")
        if not entry.get("host"):
            raise ValueError(f"Fleet entry [{i}] missing 'host'")
    return entries


def _build_auth_headers(entry: dict[str, Any]) -> dict[str, str]:
    """Return Authorization headers for entry, or {} if no auth configured."""
    auth = entry.get("auth") or {}
    bearer = auth.get("bearer") or {}
    key_env = bearer.get("key_env")
    if not key_env:
        return {}
    token = os.environ.get(key_env)
    if not token:
        raise RuntimeError(
            f"Fleet entry '{entry['name']}': auth.bearer.key_env={key_env!r} "
            "is set but the env var is not present or empty"
        )
    return {"Authorization": f"Bearer {token}"}


def run_fleet(
    entries: list[dict[str, Any]],
    repeat: int,
    results_dir: Path,
    print_fn: Callable[[str], None] = print,
) -> Path:
    """Run headless eval against all fleet entries. Returns path to JSONL output."""
    from hermia.metrics import MetricsSampler
    from hermia.results import append_result, open_run
    from hermia.runner import get_available_models, load_tests_all, run_test

    jsonl_path, csv_path = open_run(results_dir)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    tests = load_tests_all()

    old_host = os.environ.get("HERMIA_HOST")
    try:
        for idx, entry in enumerate(entries, 1):
            name = entry["name"]
            host_url = entry["host"].rstrip("/")
            headers = _build_auth_headers(entry)

            os.environ["HERMIA_HOST"] = host_url
            models = get_available_models(headers=headers)
            print_fn(
                f"[{idx}/{len(entries)}] {name} ({host_url})"
                f" — {len(models)} models, {len(tests)} tests"
            )

            sampler = MetricsSampler()
            for model_entry in models:
                model = model_entry["name"]
                for test in tests:
                    for run_index in range(repeat):
                        result = run_test(model, test, sampler, host=host_url, headers=headers)
                        result["run_id"] = run_id
                        result["run_timestamp"] = datetime.now(UTC).isoformat()
                        result["host"] = host_url
                        result["run_index"] = run_index
                        result["is_cold"] = False
                        result["cold_warm_delta_tps"] = None
                        result["consistency_pct"] = None
                        result["pass_count"] = None
                        result["robustness_n"] = None
                        append_result(result, jsonl_path, csv_path)
                        status = "✓" if not result.get("failure_reason") else "✗"
                        print_fn(f"  {status} {model}:{test['id']} ({result['elapsed_sec']}s)")
    finally:
        if old_host is not None:
            os.environ["HERMIA_HOST"] = old_host
        else:
            os.environ.pop("HERMIA_HOST", None)

    return jsonl_path
