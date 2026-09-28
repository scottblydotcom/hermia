"""Headless fleet eval runner — multi-host batch evaluation from YAML config."""

import os
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hermia.identity import IdentityCache
    from hermia.identity.salt import SaltInfo

import yaml

# Headless fleet[] schema only — TUI hosts[] uses different keys (url/engine),
# converted to this schema by _tui_fleet_to_entries before entries reach load_fleet_config's checks.
_FLEET_ENTRY_KEYS = frozenset(
    {"name", "host", "transport", "auth", "models", "stack", "test_timeout", "identity"}
)
_AUTH_KEYS = frozenset({"bearer"})
_BEARER_KEYS = frozenset({"key_env"})
_STACK_KEYS = frozenset({"gpu_arch", "runtime_version"})
_IDENTITY_KEYS = frozenset({"transport", "ssh"})


def _tui_fleet_to_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert TUI save_fleet format to headless fleet entries.

    TUI writes: hosts[]{name, url, engine, auth_header_env?, hardware?, models[]}
    Headless expects: fleet[]{name, host, transport?, auth.bearer.key_env?, models?}
    """
    hosts = data.get("hosts")
    if hosts is not None and not isinstance(hosts, list):
        raise ValueError(f"TUI fleet 'hosts' must be a list, got {type(hosts).__name__}")
    entries = []
    for h in (hosts or []):
        if not isinstance(h, dict):
            raise ValueError(
                f"TUI fleet 'hosts' entry must be a mapping, got {type(h).__name__}"
            )
        entry: dict[str, Any] = {
            "name": h.get("name"),
            "host": h.get("url"),
            "transport": h.get("engine", "ollama"),
        }
        if h.get("auth_header_env"):
            entry["auth"] = {"bearer": {"key_env": h["auth_header_env"]}}
        if h.get("models") is not None:
            entry["models"] = h["models"]
        if h.get("stack"):
            entry["stack"] = h["stack"]
        if h.get("identity") is not None:
            # Carry identity through so a TUI-format YAML honors it headlessly
            # (Fable review H2). load_fleet_config then validates it like any
            # fleet[] entry — a malformed block fails fast, a valid one stamps.
            entry["identity"] = h["identity"]
        entries.append(entry)
    return entries


def _check_nested_dict(
    value: Any, label: str, allowed: frozenset[str], i: int
) -> dict[str, Any] | None:
    """Validate an optional nested dict (e.g. entry['stack'], auth['bearer']):
    must be a mapping if present, and every key must be in `allowed`.
    Returns the dict (or None if absent) for the caller to inspect further."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(
            f"Fleet entry [{i}] '{label}' must be a mapping, got {type(value).__name__}"
        )
    unrecognized = sorted(str(k) for k in value if k not in allowed)
    if unrecognized:
        raise ValueError(
            f"Fleet entry [{i}] '{label}' has unrecognized key(s): {', '.join(unrecognized)}. "
            f"Allowed keys: {', '.join(sorted(allowed))}."
        )
    return value


def load_fleet_config(path: Path) -> list[dict[str, Any]]:
    """Parse fleet YAML. Returns list of host entries. Raises ValueError on invalid config.

    Accepts both the headless format (fleet: key) and the TUI save_fleet format
    (hosts: key) so fleets created in the TUI can be run headless without conversion.
    """
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise ValueError(f"Cannot read fleet config {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in fleet config {path}: {exc}") from exc
    entries: list[dict[str, Any]] | None
    if isinstance(data, dict) and "hosts" in data and "fleet" not in data:
        entries = _tui_fleet_to_entries(data)
    else:
        raw = data.get("fleet") if isinstance(data, dict) else None
        entries = raw if isinstance(raw, list) else None
    if not isinstance(entries, list) or not entries:
        is_tui_fmt = isinstance(data, dict) and "hosts" in data and "fleet" not in data
        key_name = "hosts" if is_tui_fmt else "fleet"
        raise ValueError(f"Fleet config must contain at least one entry under '{key_name}'")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Fleet entry [{i}] must be a mapping, got {type(entry).__name__}")
        unrecognized = sorted(str(k) for k in entry if k not in _FLEET_ENTRY_KEYS)
        if unrecognized:
            hint = (
                " (Note: 'engine' is a TUI hosts[] key — headless fleet[] entries use "
                "'transport' instead.)"
                if "engine" in unrecognized
                else ""
            )
            raise ValueError(
                f"Fleet entry [{i}] has unrecognized key(s): {', '.join(unrecognized)}. "
                f"Allowed keys: {', '.join(sorted(_FLEET_ENTRY_KEYS))}.{hint}"
            )
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
        _check_nested_dict(entry.get("stack"), "stack", _STACK_KEYS, i)
        _check_nested_dict(entry.get("identity"), "identity", _IDENTITY_KEYS, i)
        # Fail fast on a malformed identity block (bad transport, missing ssh
        # target, arg-injection target, or a reserved wmi/agent transport) at
        # load time, before any host is contacted — mirrors the test_timeout
        # inline-validation pattern. Without this the SSH-identity feature was
        # also unreachable: an unrecognized-key error rejected every identity block.
        from hermia.identity import parse_identity_transport
        parse_identity_transport(entry)
        auth = _check_nested_dict(entry.get("auth"), "auth", _AUTH_KEYS, i)
        if auth is not None:
            _check_nested_dict(auth.get("bearer"), "auth.bearer", _BEARER_KEYS, i)
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
    test_timeout: int | None = None,
    identity_cache: "IdentityCache | None" = None,
    identity_salt: "SaltInfo | None" = None,
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
    from hermia.fingerprint import FingerprintCache
    from hermia.identity import (
        IdentityCache,
        load_salt,
        parse_identity_transport,
    )
    from hermia.metrics import MetricsSampler
    from hermia.results import append_result
    from hermia.robustness import compute_reproducibility, score_rows
    from hermia.runner import (
        TEST_TIMEOUT,
        _normalize_host,
        get_available_models,
        load_tests_all,
        run_test,
    )
    from hermia.transport.ollama import OllamaTransport
    from hermia.transport.openai_compat import OpenAICompatTransport

    _identity_transport = parse_identity_transport(entry)
    # Salt is loaded ONCE per run (run_fleet) and shared; only ssh hosts need it,
    # so an api host never mints ~/.hermia salt even inside a mixed fleet. In the
    # ephemeral fallback load_salt() returns a fresh random salt each call, so a
    # per-host call would derive incomparable ids for one machine within a run.
    _identity_salt: SaltInfo | None = None
    if _identity_transport.kind == "ssh":
        _identity_salt = identity_salt if identity_salt is not None else load_salt()
    _id_cache = identity_cache or IdentityCache()

    # Priority: caller-supplied (CLI flag) > per-host YAML key > module default.
    if test_timeout is not None:
        effective_timeout: int = test_timeout
    elif "test_timeout" not in entry:
        effective_timeout = TEST_TIMEOUT
    else:
        _yaml_timeout = entry["test_timeout"]
        if isinstance(_yaml_timeout, bool) or not isinstance(_yaml_timeout, int) \
                or _yaml_timeout < 1:
            raise ValueError(
                f"host '{entry.get('name')}': 'test_timeout' must be a positive integer,"
                f" got {_yaml_timeout!r}"
            )
        effective_timeout = _yaml_timeout

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

    # Engine-security posture — surface CVE / stale-server warnings before we
    # start driving traffic at the host. Fleet mode suppresses local-only
    # advisories (e.g. Ollama's unpatched /api/create) since a remote fleet
    # host is not the operator's own loopback surface. Advisory-only: never
    # let a malformed /api/version response kill the host eval.
    from hermia.preflight import check_engine_security
    try:
        sec_warnings = check_engine_security(
            host_url, transport_type, fleet_mode=True, headers=headers
        )
    except Exception as exc:  # noqa: BLE001 — advisory-only, degrade quietly
        sec_warnings = [f"SEC ⚠ engine-security probe failed: {exc}"]
    if sec_warnings:
        with print_lock:
            for w in sec_warnings:
                stderr_fn(f"  {name}: {w}")

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
    fp_cache = FingerprintCache()
    for model_entry in models:
        model = model_entry["name"]
        declared = entry.get("stack")
        fingerprint, provenance = fp_cache.get_or_probe(
            host_url, model, declared, headers=headers, engine=transport_type,
        )
        for test in tests:
            run_results: list[dict[str, Any]] = []
            for run_index in range(1, repeat + 1):
                result = run_test(
                    model, test, sampler,
                    host=host_url, headers=headers, transport=host_transport,
                    locality="remote", fp_cache=fp_cache,
                    test_timeout=effective_timeout,
                    identity_transport=_identity_transport,
                    identity_salt=_identity_salt,
                    identity_cache=_id_cache,
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
                result["stack_fingerprint"] = fingerprint
                result["_provenance"] = provenance
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
    test_timeout: int | None = None,
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

    from hermia.identity import IdentityCache, load_salt, parse_identity_transport
    _shared_identity_cache = IdentityCache()
    # Only mint/read ~/.hermia salt when a host actually opts into ssh identity;
    # an api-only fleet must not create the salt file as a side effect.
    _needs_identity = any(parse_identity_transport(e).kind == "ssh" for e in entries)
    _shared_identity_salt = load_salt() if _needs_identity else None
    if _shared_identity_salt is not None and not _shared_identity_salt.is_stable:
        stderr_fn(
            "  WARNING: machine-identity salt is EPHEMERAL (could not persist "
            "~/.hermia salt) — machine_fingerprints will differ every run and are "
            "not comparable across runs. Set HERMIA_FLEET_SALT to stabilize."
        )

    def run_group(group: list[dict[str, Any]]) -> tuple[int, int]:
        # Returns (evaluated, skipped). Counts are returned (not shared mutable
        # state) so concurrent groups stay thread-safe.
        evaluated = 0
        skipped = 0
        for entry in group:  # same physical host → strictly sequential
            if _run_host_eval(
                entry, repeat, run_id, jsonl_path, csv_path,
                print_lock, print_fn, stderr_fn, verbosity,
                test_timeout=test_timeout,
                identity_cache=_shared_identity_cache,
                identity_salt=_shared_identity_salt,
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
