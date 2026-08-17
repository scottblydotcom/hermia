"""Tests for the default-deny anonymizer — privacy core.

The critical invariants:
1. All FORBIDDEN_KEYS are dropped unconditionally.
2. Only SUBMIT_WHITELIST + {"failure_category", "hermia_version"} keys appear in output.
3. failure_reason is reduced to a category prefix — no host/IP detail survives.
4. No forbidden VALUE appears anywhere in repr(output).
5. Unknown future fields never leak (default-deny).

A passthrough implementation would fail tests 2 and 5.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from hermia.sink.anonymize import SUBMIT_WHITELIST, anonymize_row

FORBIDDEN_KEYS = {
    "host",
    "fleet_host_name",
    "fleet_host_start",
    "raw_prompt",
    "raw_response",
    "raw_system",
    "output_preview",
    "run_id",
    "run_timestamp",
    "peak_cpu_pct",
    "peak_ram_used_gb",
    "peak_gpu_pct",
    "peak_vram_used_gb",
}

# The complete set of keys the anonymizer is ever allowed to emit.
_ALLOWED_OUTPUT_KEYS = SUBMIT_WHITELIST | {"failure_category", "hermia_version", "git_sha"}


# ---------------------------------------------------------------------------
# Deterministic unit tests
# ---------------------------------------------------------------------------


def test_anonymize_drops_all_forbidden_keys() -> None:
    """Every forbidden key must be absent from the output."""
    row: dict[str, object] = {k: "SENSITIVE" for k in FORBIDDEN_KEYS}
    row.update({"model": "qwen2.5:32b", "tokens": 10})
    out = anonymize_row(row)
    assert FORBIDDEN_KEYS.isdisjoint(out.keys())


def test_anonymize_only_whitelisted_keys_plus_derived() -> None:
    """Default-deny: unknown future fields (not in whitelist) never leak."""
    row: dict[str, object] = {
        **{k: 1 for k in SUBMIT_WHITELIST},
        "host": "server-01",
        "raw_response": "some text",
        "surprise_new_field": "should_not_appear",
    }
    out = anonymize_row(row)
    # Only whitelisted + derived keys allowed — future unknown fields must NOT appear.
    assert set(out).issubset(_ALLOWED_OUTPUT_KEYS)
    assert "surprise_new_field" not in out


def test_failure_reason_reduced_to_category() -> None:
    """failure_reason is reduced to a category; host/IP detail must not survive."""
    out = anonymize_row(
        {"failure_reason": "ERROR: HTTPConnectionPool(host='192.168.1.5', port=11434)"}
    )
    assert out["failure_category"] == "ERROR"
    assert "192.168" not in str(out)
    assert "failure_reason" not in out


def test_failure_reason_schema_fail_category() -> None:
    out = anonymize_row({"failure_reason": "SCHEMA_FAIL: missing required field"})
    assert out["failure_category"] == "SCHEMA_FAIL"
    assert "missing required field" not in str(out)


def test_failure_reason_retry_exhausted_category() -> None:
    # Must stay a distinct category from API_ERROR/OLLAMA_ERROR so bulk
    # analysis can separate infra-retry noise from behavioral failures.
    out = anonymize_row({"failure_reason": "RETRY_EXHAUSTED: after 3 attempts: HTTP 503"})
    assert out["failure_category"] == "RETRY_EXHAUSTED"


def test_failure_reason_none_gives_none_category() -> None:
    out = anonymize_row({"failure_reason": None})
    assert out["failure_category"] == "none"


def test_failure_reason_absent_gives_none_category() -> None:
    out = anonymize_row({"model": "x"})
    assert out["failure_category"] == "none"


def test_failure_reason_unknown_gives_other_category() -> None:
    out = anonymize_row({"failure_reason": "completely_unknown_prefix: detail"})
    assert out["failure_category"] == "other"


def test_failure_reason_content_leak_category() -> None:
    """CONTENT_LEAK (hermia-m12 / -7ed) must map to its own category, not 'other'.

    Downstream corpus-audit and TUI badges distinguish content leaks from
    generic failures; falling into 'other' silently hides a security-relevant
    row.
    """
    out = anonymize_row({"failure_reason": "CONTENT_LEAK"})
    assert out["failure_category"] == "CONTENT_LEAK"


def test_failure_reason_empty_content_with_thinking_category() -> None:
    """EMPTY_CONTENT_WITH_THINKING (hermia-cv5z) must map to its own category, not
    'other' — else 'reasoned-but-no-answer' is indistinguishable from generic
    unclassified failures in the shared/aggregated dataset."""
    out = anonymize_row({"failure_reason": "EMPTY_CONTENT_WITH_THINKING"})
    assert out["failure_category"] == "EMPTY_CONTENT_WITH_THINKING"


def test_no_sensitive_value_survives() -> None:
    """The actual sentinel VALUE must not appear anywhere in the output repr."""
    sentinel = "host-marker-9f3a2c"
    row: dict[str, object] = {
        "host": sentinel,
        "raw_response": sentinel,
        "output_preview": sentinel,
        "model": "m",
        "tokens": 1,
    }
    out = anonymize_row(row)
    assert sentinel not in repr(out)


def test_hermia_version_stamped() -> None:
    """The output must always carry hermia_version."""
    out = anonymize_row({"model": "x"})
    assert "hermia_version" in out
    assert out["hermia_version"]  # non-empty


def test_git_sha_stamped() -> None:
    """The output must always carry git_sha (hermia-c38b provenance fix)."""
    out = anonymize_row({"model": "x"})
    assert "git_sha" in out
    assert out["git_sha"]  # non-empty


def test_whitelist_fields_pass_through() -> None:
    """Whitelisted fields that are present must appear in the output unchanged."""
    row: dict[str, object] = {"model": "qwen2.5:32b", "tokens": 42, "score": 0.9}
    out = anonymize_row(row)
    assert out["model"] == "qwen2.5:32b"
    assert out["tokens"] == 42
    assert out["score"] == 0.9


def test_passthrough_would_fail() -> None:
    """Verify the test would catch a naive passthrough implementation.

    If anonymize_row were a no-op passthrough (returning the input dict), the
    forbidden key "host" would appear in the output — which our other tests
    already forbid. This test exists as explicit documentation of that contract.
    """
    row: dict[str, object] = {"host": "LEAKS", "model": "x"}
    out = anonymize_row(row)
    # A passthrough would have "host" here — we verify it does NOT.
    assert "host" not in out


def test_signals_non_bool_values_are_stripped() -> None:
    """Non-bool values in signals (e.g. leaked host strings) must be stripped."""
    row = {
        "model": "m",
        "signals": {"flag": True, "leaked_host": "192.168.1.5", "detail": "raw text"},
    }
    out = anonymize_row(row)
    assert out["signals"] == {"flag": True}
    assert "192.168" not in repr(out)
    assert "raw text" not in repr(out)


def test_signals_non_dict_is_dropped() -> None:
    """A signals value that is not a dict must be dropped entirely."""
    out = anonymize_row({"model": "m", "signals": "host=192.168.1.5 raw=SENSITIVE"})
    assert "signals" not in out
    assert "192.168" not in repr(out)
    assert "SENSITIVE" not in repr(out)


def test_frameworks_unknown_keys_stripped() -> None:
    """Only known taxonomy keys survive; unknown keys with identifying data are dropped."""
    row = {
        "model": "m",
        "frameworks": {
            "owasp_llm_top10_2025": ["LLM01:2025"],
            "custom_sentinel": ["scott-lab-internal-id-12345"],
            "mitre_atlas_v5_1": ["AML.T0051"],
        },
    }
    out = anonymize_row(row)
    assert "custom_sentinel" not in out["frameworks"]
    assert "scott-lab" not in repr(out)
    assert out["frameworks"] == {
        "owasp_llm_top10_2025": ["LLM01:2025"],
        "mitre_atlas_v5_1": ["AML.T0051"],
    }


def test_frameworks_non_string_list_values_stripped() -> None:
    """Framework values that aren't list-of-strings are dropped."""
    row = {
        "model": "m",
        "frameworks": {
            "owasp_llm_top10_2025": ["LLM01:2025"],
            "csa_maestro": "not-a-list",
            "nist_ai_rmf": [123, "ME 2.3"],
        },
    }
    out = anonymize_row(row)
    assert out["frameworks"] == {"owasp_llm_top10_2025": ["LLM01:2025"]}


def test_frameworks_non_dict_is_dropped() -> None:
    """A frameworks value that is not a dict must be dropped entirely."""
    out = anonymize_row({"model": "m", "frameworks": "owasp=SENSITIVE"})
    assert "frameworks" not in out
    assert "SENSITIVE" not in repr(out)


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------


@given(
    # Use a fixed prefix that cannot appear in legitimate output fields
    # (version strings, model names, etc.) so value-leak checks are reliable.
    forbidden_suffixes=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=6,
        max_size=14,
    ),
    extra_keys=st.lists(
        st.text(min_size=1, max_size=12).filter(
            lambda k: k not in FORBIDDEN_KEYS and k not in SUBMIT_WHITELIST
        ),
        max_size=3,
    ),
)
@settings(max_examples=200)
def test_property_no_forbidden_key_or_value_leaks(
    forbidden_suffixes: str,
    extra_keys: list[str],
) -> None:
    """For any dict that includes forbidden keys with sentinel values:
    1. None of those forbidden keys appear in the output.
    2. None of the sentinel values appear in repr(output).
    3. Any extra unknown keys are also dropped.
    """
    # Build sentinel values with a guaranteed-unique prefix that cannot
    # appear naturally in version strings, model names, or other output.
    _SENTINEL_PREFIX = "TESTLEAK_XZQJ_"
    forbidden_vals = {
        k: _SENTINEL_PREFIX + forbidden_suffixes
        for k in FORBIDDEN_KEYS
    }
    extra = {k: _SENTINEL_PREFIX + "extra" for k in extra_keys}
    row: dict[str, object] = {**forbidden_vals, **extra, "model": "test-model"}
    out = anonymize_row(row)

    # No forbidden key in output
    assert FORBIDDEN_KEYS.isdisjoint(out.keys()), (
        f"Forbidden key leaked: {FORBIDDEN_KEYS & set(out.keys())}"
    )

    # No sentinel value in repr(out) — verifies value-level privacy
    out_repr = repr(out)
    for val in forbidden_vals.values():
        assert val not in out_repr, f"Forbidden value leaked: {val!r}"

    # Only allowed keys in output
    assert set(out).issubset(_ALLOWED_OUTPUT_KEYS), (
        f"Non-whitelisted key in output: {set(out) - _ALLOWED_OUTPUT_KEYS}"
    )


# ---------------------------------------------------------------------------
# machine_id pseudonymisation (hermia-cfqv)
# ---------------------------------------------------------------------------


def test_machine_id_is_not_whitelisted():
    """Default-deny must keep the salted hash out of community submissions."""
    from hermia.sink.anonymize import SUBMIT_WHITELIST

    assert "machine_id" not in SUBMIT_WHITELIST
    assert "machine_id_basis" not in SUBMIT_WHITELIST


def test_pseudonyms_are_stable_and_ordered_by_first_appearance():
    from hermia.sink.anonymize import assign_machine_pseudonyms

    rows = [{"machine_id": "bbbb"}, {"machine_id": "aaaa"}, {"machine_id": "bbbb"}]
    got = assign_machine_pseudonyms(rows)
    assert [r["machine_pseudonym"] for r in got] == ["node-a", "node-b", "node-a"]


def test_null_machine_id_gets_null_pseudonym_not_a_node_name():
    from hermia.sink.anonymize import assign_machine_pseudonyms

    got = assign_machine_pseudonyms([{"machine_id": None}])
    assert got[0]["machine_pseudonym"] is None


def test_absent_machine_id_key_yields_null_pseudonym():
    from hermia.sink.anonymize import assign_machine_pseudonyms

    got = assign_machine_pseudonyms([{"model": "x"}])
    assert got[0]["machine_pseudonym"] is None


def test_original_machine_id_is_removed_from_the_output():
    from hermia.sink.anonymize import assign_machine_pseudonyms

    got = assign_machine_pseudonyms([{"machine_id": "aaaa"}])
    assert "machine_id" not in got[0]


def test_input_rows_are_not_mutated():
    from hermia.sink.anonymize import assign_machine_pseudonyms

    rows = [{"machine_id": "aaaa"}]
    assign_machine_pseudonyms(rows)
    assert rows[0]["machine_id"] == "aaaa"


def test_pseudonyms_extend_past_z():
    from hermia.sink.anonymize import assign_machine_pseudonyms

    rows = [{"machine_id": f"id{i:03d}"} for i in range(28)]
    got = assign_machine_pseudonyms(rows)
    names = [r["machine_pseudonym"] for r in got]
    assert names[0] == "node-a"
    assert names[25] == "node-z"
    assert len(set(names)) == 28
