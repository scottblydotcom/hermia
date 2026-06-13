"""hermia submit — anonymize and POST results to the community dataset.

Opt-in: nothing is sent unless the user explicitly runs ``hermia-submit``.
A confirmation prompt is shown before every live submission unless ``--yes``
is passed.  ``--dry-run`` prints the payload to stdout without any network I/O.

Auth: v0.2 uses no client auth (Pattern A).  The endpoint is open; defense is
handled server-side via Reserved Concurrency, per-IP throttle, kill switch, and
budget alarms.  The ``install_id`` field is a stable per-install UUID stored at
``~/.hermia/config.toml`` so the server can associate submissions without any PII.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any
from uuid import uuid4

import psutil
import requests

from hermia import __version__
from hermia.metrics import detect_gpu
from hermia.results import load_jsonl
from hermia.sink.anonymize import anonymize_row

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".hermia"
CONFIG_PATH = CONFIG_DIR / "config.toml"
RESULTS_DIR = Path("results")
CORPUS_VERSION = "v0.2"
SUBMIT_URL = "https://hermia.scottbly.com/v1/submit"

# Value-level anonymization patterns (mirror lambda/anonymization.py)
_URL_PATTERN = re.compile(r"https?://|://")
_PATH_PREFIXES = ("/Users/", "/home/", "C:\\")
# Redact the user-home dir INCLUDING the username segment. Redacting the prefix
# alone leaves the username exposed (e.g. "scott" in "/Users/scott/...") — a
# privacy leak in a community dataset.
# Match the whole user-dir segment up to the next path separator (NOT stopping
# at whitespace) so usernames with spaces (e.g. "C:\Users\Scott Bly") are fully
# redacted. Bias is intentionally toward over-redaction for a privacy tool.
_PATH_USER_PATTERN = re.compile(
    r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([^/\\]+)", re.IGNORECASE
)
_TILDE_PATTERN = re.compile(r"(?:^|(?<=\s))~/")
_HOSTNAME_PATTERN = re.compile(
    r"\b\w[\w.-]*\.(?:local|internal|lan|home|localdomain)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# install_id management
# ---------------------------------------------------------------------------


def load_or_create_install_id(config_path: Path | None = None) -> str:
    """Load install_id from config or create and persist a new one.

    The config file is TOML:

        [hermia]
        install_id = "<uuid4>"

    Parsed with the stdlib ``tomllib`` (Python 3.11+) so a hand-edited file
    with comments or reordered keys is read correctly. A malformed file is
    treated as absent and regenerated.

    Parameters
    ----------
    config_path:
        Override path for testing.  Defaults to ``~/.hermia/config.toml``.
    """
    if config_path is None:
        config_path = CONFIG_PATH

    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
        existing = data.get("hermia", {}).get("install_id")
        if isinstance(existing, str) and existing:
            return existing
    except FileNotFoundError:
        pass
    except tomllib.TOMLDecodeError:
        pass  # malformed/hand-broken config — fall through and regenerate

    install_id = str(uuid4())
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            f'[hermia]\ninstall_id = "{install_id}"\n', encoding="utf-8"
        )
    except OSError:
        # Read-only / permission-restricted home (e.g. locked-down container):
        # use the id for this run without persisting. It won't be stable across
        # runs, but the CLI still works instead of crashing.
        pass
    return install_id


# ---------------------------------------------------------------------------
# host_class mapping
# ---------------------------------------------------------------------------

_NVIDIA_MATCHERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"RTX\s+5090"), "local:cuda/rtx-5090"),
    (re.compile(r"RTX\s+4090"), "local:cuda/rtx-4090"),
    (re.compile(r"RTX\s+3090"), "local:cuda/rtx-3090"),
    (re.compile(r"RTX\s+30[5678]0"), "local:cuda/rtx-30xx"),
    (re.compile(r"RTX\s+A\d"), "local:cuda/rtx-a-series"),
    (re.compile(r"GTX\s+(?:9|10)\d\d"), "local:cuda/gtx-legacy"),
]

_APPLE_MATCHERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bM1\b"), "local:metal/m1"),
    (re.compile(r"\bM2\b"), "local:metal/m2"),
    (re.compile(r"\bM3\b"), "local:metal/m3"),
    (re.compile(r"\bM4\b"), "local:metal/m4"),
]


def compute_host_class(gpu_info: dict[str, Any]) -> str:
    """Map detect_gpu() result to the 17-value host_class vocabulary.

    Falls back to ``local:other`` whenever no rule matches — the server
    accepts this value and surfaces it for manual taxonomy expansion.
    """
    vendor: str = gpu_info.get("vendor", "none")
    card: str = gpu_info.get("card", "")

    if vendor == "nvidia":
        for pattern, cls in _NVIDIA_MATCHERS:
            if pattern.search(card):
                return cls
        return "local:other"

    if vendor == "apple":
        for pattern, cls in _APPLE_MATCHERS:
            if pattern.search(card):
                return cls
        return "local:other"

    if vendor == "amd":
        card_upper = card.upper()
        if any(x in card_upper for x in ("7900", "7800", "7700")):
            return "local:rocm/rdna3"
        if any(x in card_upper for x in ("6900", "6800", "6700", "6600", "6500", "6400")):
            return "local:rocm/rdna2"
        if card_upper.startswith("MI"):
            return "local:rocm/instinct"
        return "local:vulkan/amd"

    if vendor == "intel":
        return "local:vulkan/intel-igpu"

    if vendor == "none":
        return "local:cpu"

    return "local:other"


# ---------------------------------------------------------------------------
# unified_memory_gb
# ---------------------------------------------------------------------------


def compute_unified_memory_gb(gpu_info: dict[str, Any]) -> float | None:
    """Return unified memory (Apple) or discrete VRAM in GB, or None on failure.

    For Intel iGPU and CPU-only systems, falls back to total system RAM via
    psutil.  Returns None if all attempts fail so the server can decide whether
    to reject the submission.
    """
    vendor: str = gpu_info.get("vendor", "none")
    vram: float = gpu_info.get("vram_total_gb", 0.0)

    try:
        if vendor in ("nvidia", "amd"):
            # Discrete GPUs do NOT share system RAM. If VRAM detection failed
            # (vram == 0.0), report None rather than a misleading system-RAM
            # figure — let the server decide how to handle the missing value.
            return float(vram) if vram > 0.0 else None
        if vendor == "apple" and vram > 0.0:
            # Apple Silicon: unified memory == measured VRAM when available.
            return float(vram)
        # Apple w/o measured VRAM, Intel iGPU, and CPU-only systems: total
        # system RAM is the meaningful figure.
        return float(psutil.virtual_memory().total) / (1024 ** 3)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Client-side anonymization (mirrors lambda/anonymization.py rule set)
# ---------------------------------------------------------------------------


def _redact_string(value: str, field_path: str = "") -> str:
    """Replace forbidden URL/path/hostname patterns with ``[REDACTED]``.

    Parameters
    ----------
    value:
        The string to sanitize.
    field_path:
        Dot-separated path used for exemption checks:
        - ``'extras_json'`` or paths ending in ``'.extras_json'``: fully exempt.
        - ``'attribution.url'``: URL patterns are exempt (URLs are valid there).
    """
    if field_path == "extras_json" or field_path.endswith(".extras_json"):
        return value

    is_attribution_url = field_path == "attribution.url"

    if not is_attribution_url and _URL_PATTERN.search(value):
        value = _URL_PATTERN.sub("[REDACTED]", value)

    # Redact home dir + username first (prefix-only redaction would leak the
    # username), then collapse any remaining bare prefixes (e.g. non-user C:\ paths).
    value = _PATH_USER_PATTERN.sub("[REDACTED]", value)
    if any(prefix in value for prefix in _PATH_PREFIXES):
        for prefix in _PATH_PREFIXES:
            value = value.replace(prefix, "[REDACTED]")

    value = _TILDE_PATTERN.sub("[REDACTED]", value)

    if _HOSTNAME_PATTERN.search(value):
        value = _HOSTNAME_PATTERN.sub("[REDACTED]", value)

    return value


def _redact_node(node: Any, path: str) -> Any:
    """Recursively redact a value at the given dot-path."""
    if isinstance(node, str):
        return _redact_string(node, path)
    if isinstance(node, dict):
        return {
            k: _redact_node(v, f"{path}.{k}" if path else k)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_redact_node(item, f"{path}[{i}]") for i, item in enumerate(node)]
    return node


def anonymize_for_submit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply anonymize_row (whitelist + key-stripping) then redact value patterns.

    Two passes:
    1. ``anonymize_row`` enforces the default-deny whitelist and strips forbidden
       keys (host, fleet_host_name, output_preview, raw_response).
    2. ``_redact_node`` replaces URL/path/hostname patterns in any remaining strings.
    """
    result: list[dict[str, Any]] = []
    for row in rows:
        clean = anonymize_row(row)
        result.append({k: _redact_node(v, k) for k, v in clean.items()})
    return result


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------


def build_payload(
    install_id: str,
    host_class: str,
    unified_memory_gb: float | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the v0.2 submission JSON envelope.

    The shape is forward-compatible with v0.3 (Pattern B token auth is purely
    additive — ``install_id`` is never renamed, the envelope is never restructured).
    """
    return {
        "install_id": install_id,
        "hermia_version": __version__,
        "corpus_version": CORPUS_VERSION,
        "host_class": host_class,
        "unified_memory_gb": unified_memory_gb,
        "attribution": None,
        "rows": rows,
        "extras_json": None,
    }


# ---------------------------------------------------------------------------
# Main submit logic
# ---------------------------------------------------------------------------


def _find_latest_results() -> Path | None:
    """Return the most recently modified JSONL file in RESULTS_DIR, or None."""
    candidates = list(RESULTS_DIR.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def submit_command(
    results_path: Path | None,
    dry_run: bool,
    yes: bool,
) -> None:
    """Main entry point for ``hermia-submit``.

    Loads results, anonymizes them, assembles the payload, and either prints it
    (dry-run) or POSTs to the submission endpoint with a confirmation prompt.
    Calls ``sys.exit(1)`` on any unrecoverable error.
    """
    # Resolve results path
    if results_path is None:
        results_path = _find_latest_results()
        if results_path is None:
            print("hermia submit: no results found in results/ directory", file=sys.stderr)
            sys.exit(1)

    # Load rows
    try:
        rows = load_jsonl(results_path)
    except OSError as exc:
        print(f"hermia submit: cannot read results: {exc}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print(f"hermia submit: no rows in {results_path}", file=sys.stderr)
        sys.exit(1)

    # Detect hardware
    gpu_info = detect_gpu()
    host_class = compute_host_class(gpu_info)
    unified_memory_gb = compute_unified_memory_gb(gpu_info)

    # Anonymize
    anonymized_rows = anonymize_for_submit(rows)

    # Resolve install_id
    install_id = load_or_create_install_id()

    # Build payload
    payload = build_payload(install_id, host_class, unified_memory_gb, anonymized_rows)

    if dry_run:
        print(json.dumps(payload, indent=2))
        return

    # Confirmation prompt
    if not yes:
        print(
            f"About to submit {len(rows)} test results "
            f"(host_class={host_class}, {len(anonymized_rows)} rows)"
        )
        print("Type 'y' to proceed: ", end="", flush=True)
        try:
            answer = input()
        except EOFError:
            answer = ""
        if answer.strip() != "y":
            print("Aborted.")
            sys.exit(0)

    # POST
    try:
        resp = requests.post(SUBMIT_URL, json=payload, timeout=30)
    except requests.exceptions.RequestException as exc:
        print(f"hermia submit: network error: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 503:
        print(
            "hermia submit: submissions are temporarily disabled — try again later.",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 429:
        print("hermia submit: rate limited — wait a few minutes.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code >= 400:
        body_snippet = resp.text[:200]
        print(
            f"hermia submit: server rejected submission: {body_snippet}",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 201:
        try:
            data = resp.json()
        except ValueError:
            data = None
        # A valid-but-non-dict JSON body (list/string/bool) must not crash on .get().
        public_url = (
            data.get("public_url", "(no URL returned)")
            if isinstance(data, dict)
            else "(could not parse response)"
        )
        print(f"Submitted. Public URL: {public_url}")
    else:
        print(
            f"hermia submit: unexpected response status {resp.status_code}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and call submit_command."""
    parser = argparse.ArgumentParser(
        prog="hermia-submit",
        description="Anonymize and submit hermia results to the community dataset.",
    )
    parser.add_argument(
        "--results",
        type=Path,
        metavar="FILE",
        default=None,
        help="Path to a JSONL results file (default: most recent in results/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the anonymized payload without sending it",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    args = parser.parse_args()
    submit_command(
        results_path=args.results,
        dry_run=args.dry_run,
        yes=args.yes,
    )


if __name__ == "__main__":
    main()
