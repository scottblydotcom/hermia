"""Default-deny anonymizer for community submission.

A row is anonymized by copying ONLY an explicit whitelist of safe fields.
Everything else is dropped. ``failure_reason`` is reduced to a category
prefix (it can contain ``ERROR: ...<host/IP>...`` detail that must not be
shared). Auth tokens, hostnames, IPs, raw prompt/response text,
local-client hardware metrics, and run ids/timestamps are never emitted.

The privacy guarantee is enforced by the default-deny whitelist: any field
not in SUBMIT_WHITELIST is unconditionally excluded. Unknown fields added
to result rows in future versions of hermia are therefore also excluded
automatically — they cannot leak.
"""
from __future__ import annotations

from typing import Any

from hermia import __git_sha__, __version__

# Explicit whitelist of fields safe to share.  Default-deny: anything NOT
# listed here is dropped, including future fields not yet imagined.
SUBMIT_WHITELIST: frozenset[str] = frozenset(
    {
        "model",
        "dimension",
        "test_id",
        "frameworks",
        "json_valid",
        "schema_compliant",
        "had_markdown_fence",
        "tokens",
        "elapsed_sec",
        "tokens_per_sec",
        "mode",
        "orchestration",
        "orchestration_version",
        "execution_path",
        "vram_server_gb",
        "model_size_server_gb",
        "score",
        "consistency_pct",
        "pass_count",
        "robustness_n",
        "run_index",
        "is_cold",
        "cold_warm_delta_tps",
        "signals",
        "corpus_sha256",
    }
)

# Category prefixes for failure_reason reduction.  Longest matches first to
# avoid SCHEMA_FAIL being incorrectly categorised as the shorter "ERROR".
_KNOWN_FAILURE_PREFIXES: tuple[str, ...] = (
    "SCHEMA_FAIL",
    "JSON_PARSE_ERROR",
    "EMPTY_RESPONSE",
    "CONTENT_LEAK",
    "TIMEOUT",
    "RETRY_EXHAUSTED",
    "OLLAMA_ERROR",
    "API_ERROR",
    "ERROR",
)


_KNOWN_FRAMEWORK_KEYS: frozenset[str] = frozenset(
    {"owasp_llm_top10_2025", "mitre_atlas_v5_1", "csa_maestro", "nist_ai_rmf"}
)


def _categorize_failure(reason: object) -> str:
    """Reduce a failure_reason string to its category prefix.

    Strips all detail that might contain host names, IPs, or other
    identifying information.  Returns ``"none"`` when reason is absent
    or empty, and ``"other"`` for unrecognised prefixes.
    """
    if not reason or not isinstance(reason, str):
        return "none"
    for prefix in _KNOWN_FAILURE_PREFIXES:
        if reason.startswith(prefix):
            return prefix
    return "other"


def anonymize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return an anonymized copy of *row* safe for community submission.

    Only whitelisted fields are copied.  ``failure_reason`` is replaced by
    ``failure_category`` (the prefix only).  The Hermia version and git
    commit are stamped in ``hermia_version`` and ``git_sha``.  No host
    identity, raw text, client hardware metrics, run ids, or timestamps
    are ever emitted.
    """
    out: dict[str, Any] = {k: row[k] for k in SUBMIT_WHITELIST if k in row}

    # Value-level default-deny for signals: only bool values are safe to share.
    # A probe could embed host/IP strings or other sensitive content in non-bool
    # signal values; strip anything that is not strictly bool.
    sig = out.get("signals")
    if isinstance(sig, dict):
        out["signals"] = {k: v for k, v in sig.items() if isinstance(v, bool)}
    else:
        out.pop("signals", None)  # drop if not a bool dict

    # Value-level default-deny for frameworks: only known taxonomy keys with
    # list-of-strings values are safe.  A custom dataset could embed identifying
    # strings in framework values; strip anything outside the known shape.
    if "frameworks" in out:
        fw = out["frameworks"]
        if isinstance(fw, dict):
            out["frameworks"] = {
                k: list(fw[k])
                for k in _KNOWN_FRAMEWORK_KEYS
                if k in fw
                and isinstance(fw[k], list)
                and all(isinstance(item, str) for item in fw[k])
            }
        else:
            del out["frameworks"]

    out["failure_category"] = _categorize_failure(row.get("failure_reason"))
    out["hermia_version"] = __version__
    out["git_sha"] = __git_sha__
    return out
