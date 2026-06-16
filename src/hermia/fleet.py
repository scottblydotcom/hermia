"""Headless fleet eval runner — multi-host batch evaluation from YAML config."""

import os
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def load_fleet_config(path: Path) -> list[dict[str, Any]]:
    """Parse fleet YAML. Returns list of host entries. Raises ValueError on invalid config."""
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise ValueError(f"Cannot read fleet config {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in fleet config {path}: {exc}") from exc
    entries = data.get("fleet") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("Fleet config must contain at least one entry under 'fleet'")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Fleet entry [{i}] must be a mapping, got {type(entry).__name__}")
        if not isinstance(entry.get("name"), str) or not entry["name"]:
            raise ValueError(f"Fleet entry [{i}] missing or invalid 'name'")
        if not isinstance(entry.get("host"), str) or not entry["host"]:
            raise ValueError(f"Fleet entry [{i}] missing or invalid 'host'")
        transport = entry.get("transport", "ollama")
        if transport not in ("ollama", "openai-compat"):
            raise ValueError(
                f"Fleet entry '{entry.get('name', '?')}': transport must be 'ollama' or "
                f"'openai-compat', got '{transport}'"
            )
        models = entry.get("models")
        if models is not None:
            if models == "auto":
                if transport != "openai-compat":
                    raise ValueError(
                        f"Fleet entry [{i}] 'models: auto' is only valid for "
                        "openai-compat transport (ollama auto-discovers when "
                        "'models' is omitted)"
                    )
            elif not isinstance(models, list) or not all(isinstance(m, str) for m in models):
                raise ValueError(
                    f"Fleet entry [{i}] 'models' must be a list of strings or 'auto'"
                )
        stack = entry.get("stack")
        if stack is not None and not isinstance(stack, dict):
            raise ValueError(
                f"Fleet entry [{i}] 'stack' must be a mapping, got {type(stack).__name__}"
            )
    return entries


def _build_auth_headers(entry: dict[str, Any]) -> dict[str, str]:
    """Return Authorization headers for entry, or {} if no auth configured."""
    auth = entry.get("auth")
    if not isinstance(auth, dict):
        return {}
    bearer = auth.get("bearer")
    if not isinstance(bearer, dict):
        return {}
    key_env = bearer.get("key_env")
    if not isinstance(key_env, str) or not key_env:
        return {}
    token = os.environ.get(key_env)
    if not token:
        raise RuntimeError(
            f"Fleet entry '{entry['name']}': auth.bearer.key_env={key_env!r} "
            "is set but the env var is not present or empty"
        )
    return {"Authorization": f"Bearer {token}"}


def _resolve_models(
    transport_type: str,
    requested: list[str] | None,
    all_models: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Resolve the model list to evaluate for a host.

    Returns ``(models, missing)``. For openai-compat hosts the requested names
    are used directly in **sorted** order (deterministic across runs — set
    iteration order is not). For ollama hosts the discovered list order is
    preserved and any requested-but-undiscovered names are reported as missing.
    """
    if not requested:
        return all_models, set()
    requested_set = set(requested)
    if transport_type == "openai-compat":
        return [{"name": m} for m in sorted(requested_set)], set()
    models = [m for m in all_models if m["name"] in requested_set]
    missing = requested_set - {m["name"] for m in models}
    return models, missing


def _run_host_eval(
    entry: dict[str, Any],
    repeat: int,
    run_id: str,
    jsonl_path: Path,
    csv_path: Path,
    print_lock: "threading.Lock",
    print_fn: Callable[[str], None],
    stderr_fn: Callable[[str], None],
    verbosity: int,
) -> bool:
    """Evaluate every (model, test, repeat) for one fleet host. Writes rows as it goes.

    Returns True if the host was evaluated, False if it was skipped (e.g. model
    discovery failed or no models resolved).

    Models run strictly sequentially within the host (VRAM-aware: one model loaded
    at a time). Safe to call concurrently for *different* hosts.
    """
    from dataclasses import asdict
    from datetime import UTC, datetime

    from hermia.backend import resolve_stack
    from hermia.metrics import MetricsSampler
    from hermia.results import append_result
    from hermia.robustness import compute_reproducibility, score_rows
    from hermia.runner import _normalize_host, get_available_models, load_tests_all, run_test
    from hermia.transport.ollama import OllamaTransport
    from hermia.transport.openai_compat import OpenAICompatTransport

    tests = load_tests_all()
    name = entry["name"]
    host_url = _normalize_host(entry["host"])
    try:
        headers = _build_auth_headers(entry)
    except RuntimeError as exc:
        with print_lock:
            stderr_fn(f"  ERROR: host '{name}' auth setup failed ({exc}) — skipping host")
        return False
    transport_type = entry.get("transport", "ollama")
    host_transport = (
        OpenAICompatTransport(host_url, headers)
        if transport_type == "openai-compat"
        else OllamaTransport(host_url, headers)
    )
    host_start = datetime.now(UTC).isoformat()

    requested = entry.get("models")
    if transport_type == "openai-compat" and requested == "auto":
        # openai-compat has no /api/tags, but it does serve GET /v1/models.
        try:
            # isinstance narrows the transport union (guaranteed by transport_type
            # above; the else is unreachable but keeps this type-safe).
            discovered = (
                host_transport.list_models()
                if isinstance(host_transport, OpenAICompatTransport)
                else []
            )
        except Exception as exc:  # noqa: BLE001 — warn-and-skip: network/JSON/TransportError all degrade alike
            with print_lock:
                stderr_fn(
                    f"  ERROR: openai-compat host '{name}' model discovery failed"
                    f" ({exc}) — skipping host"
                )
            return False
        if not discovered:
            with print_lock:
                stderr_fn(
                    f"  ERROR: openai-compat host '{name}' returned no models from"
                    f" /v1/models — skipping host"
                )
            return False
        models = [{"name": m} for m in sorted(set(discovered))]
        missing: set[str] = set()
    elif transport_type == "openai-compat" and requested is None:
        # Omitted entirely. An explicit-but-empty list ([]) falls through to the
        # resolver and is caught by the zero-models guard with a clearer message.
        with print_lock:
            stderr_fn(
                f"  ERROR: openai-compat host '{name}' requires an explicit"
                f" 'models:' list (or 'models: auto') in fleet YAML — skipping host"
            )
        return False
    else:
        # openai-compat hosts have no /api/tags endpoint; only discover for ollama.
        all_models = (
            get_available_models(host=host_url, headers=headers)
            if transport_type != "openai-compat"
            else []
        )
        models, missing = _resolve_models(transport_type, requested, all_models)
    if missing:
        with print_lock:
            stderr_fn(
                f"  WARNING: models not found on {name}: {', '.join(sorted(missing))}"
            )

    if not models:
        with print_lock:
            stderr_fn(f"  WARNING: no models to evaluate on '{name}' — skipping host")
        return False

    if verbosity >= 0:
        with print_lock:
            print_fn(
                f"{name} ({host_url}) — {len(models)} models, {len(tests)} tests"
            )

    sampler = MetricsSampler()
    for model_entry in models:
        model = model_entry["name"]
        for test in tests:
            run_results: list[dict[str, Any]] = []
            for run_index in range(1, repeat + 1):
                result = run_test(
                    model, test, sampler,
                    host=host_url, headers=headers, transport=host_transport,
                    locality="remote",
                )
                result["run_id"] = run_id
                result["run_timestamp"] = datetime.now(UTC).isoformat()
                result["run_index"] = run_index
                result["is_cold"] = False
                result["cold_warm_delta_tps"] = None
                result["fleet_host_name"] = name
                result["fleet_host_start"] = host_start
                result.update(resolve_stack(
                    entry, result.get("orchestration_version"),
                ))
                run_results.append(result)

            # Compute robustness + reproducibility aggregates across all repeat
            # runs for this (model, test) trial group, then stamp on every row.
            rob = score_rows(run_results)
            repro_dict = asdict(compute_reproducibility(run_results))
            for result in run_results:
                result["consistency_pct"] = rob.consistency_pct
                result["pass_count"] = rob.pass_count
                result["robustness_n"] = rob.n
                result["reproducibility"] = dict(repro_dict)
                append_result(result, jsonl_path, csv_path)

                if verbosity >= 0:
                    status = "✓" if not result.get("failure_reason") else "✗"
                    elapsed = result.get("elapsed_sec") or 0.0
                    line = f"  {status} {name}/{model}:{test['id']} ({elapsed}s)"
                    if verbosity >= 1:
                        tps = result.get("tokens_per_sec") or 0.0
                        reason = result.get("failure_reason") or ""
                        line += f"  {tps:.1f} t/s"
                        if reason:
                            line += f"  [{reason}]"
                    with print_lock:
                        print_fn(line)

    return True


def _group_entries_by_host(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group entries by normalized host URL, preserving first-seen order.

    Entries sharing a physical host are returned in one group so they run
    sequentially (VRAM-aware); distinct hosts become separate groups that may
    run concurrently.
    """
    from hermia.runner import _normalize_host

    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for entry in entries:
        key = _normalize_host(entry["host"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(entry)
    return [groups[k] for k in order]


def run_fleet(
    entries: list[dict[str, Any]],
    repeat: int,
    results_dir: Path,
    print_fn: Callable[[str], None] = print,
    stderr_fn: Callable[[str], None] = lambda msg: print(msg, file=sys.stderr),
    verbosity: int = 0,
    max_concurrency: int = 4,
) -> Path:
    """Run headless eval against all fleet entries, concurrently across hosts.

    max_concurrency caps how many distinct hosts run at once (default 4).
    Entries sharing a normalized host run sequentially within one worker.

    verbosity:
        -1  quiet   — suppress all progress; print only ``Saved: <path>`` on completion
         0  normal  — host headers + per-test pass/fail lines  (default)
         1  verbose — normal output + t/s and failure_reason detail per test
    """
    from concurrent.futures import ThreadPoolExecutor

    from hermia.results import open_run

    jsonl_path, csv_path = open_run(results_dir)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print_lock = threading.Lock()

    groups = _group_entries_by_host(entries)
    workers = max(1, min(max_concurrency, len(groups)))

    def run_group(group: list[dict[str, Any]]) -> tuple[int, int]:
        # Returns (evaluated, skipped). Counts are returned (not shared mutable
        # state) so concurrent groups stay thread-safe.
        evaluated = 0
        skipped = 0
        for entry in group:  # same physical host → strictly sequential
            if _run_host_eval(
                entry, repeat, run_id, jsonl_path, csv_path,
                print_lock, print_fn, stderr_fn, verbosity,
            ):
                evaluated += 1
            else:
                skipped += 1
        return evaluated, skipped

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_group, groups))

    total_evaluated = sum(r[0] for r in results)
    total_skipped = sum(r[1] for r in results)
    # Quiet mode (-1) keeps stdout to just "Saved:"; per-host skip warnings still
    # surface on stderr, so quiet automation is not blind to skips.
    if total_skipped > 0 and verbosity >= 0:
        print_fn(f"Evaluated {total_evaluated} host(s), skipped {total_skipped}")

    print_fn(f"Saved: {jsonl_path}")
    return jsonl_path
