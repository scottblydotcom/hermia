"""Regression tests for the 8 confirmed code-review findings on Workstream A.

Each test maps to a finding from the PR #87 review (transport abstraction).
Written test-first (red) before the fixes were applied.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermia.transport.base import Response

_BASE_TEST = {
    "id": "tool-calling-basic",
    "dimension": "tool-use",
    "description": "basic tool call",
    "system": "You are a helpful assistant.",
    "prompt": "Call the get_weather tool for London.",
}

_PS_EMPTY = {"vram_server_gb": None, "model_size_server_gb": None}


def _mock_sampler() -> MagicMock:
    s = MagicMock()
    s.peak.return_value = {
        "cpu_pct": 10.0, "ram_used_gb": 8.0, "gpu_pct": 85.0, "vram_used_gb": 20.0,
    }
    return s


# ── Finding #2: eval_count / completion_tokens null → tokens must coerce to 0 ──

def test_ollama_eval_count_null_yields_zero_tokens() -> None:
    """Ollama may send eval_count: null; .get(default) does not catch null → must coerce."""
    from hermia.transport.ollama import OllamaTransport

    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "hi"},
            "eval_count": None,
            "done": True,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        resp = transport.generate("m", [{"role": "user", "content": "hi"}])
        assert resp.tokens == 0


def test_openai_completion_tokens_null_yields_zero_tokens() -> None:
    from hermia.transport.openai_compat import OpenAICompatTransport

    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "hi"}}],
            "usage": {"completion_tokens": None, "total_tokens": None},
        }
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        resp = transport.generate("m", [{"role": "user", "content": "hi"}])
        assert resp.tokens == 0


# ── Gemini follow-up: defensive guards against malformed backend JSON ─────────

def test_ollama_non_dict_message_does_not_crash() -> None:
    """A malformed backend may return message as a non-dict; must not AttributeError."""
    from hermia.transport.ollama import OllamaTransport

    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {"message": "oops-not-a-dict", "eval_count": 3}
        transport = OllamaTransport(base_url="http://localhost:11434")
        resp = transport.generate("m", [{"role": "user", "content": "hi"}])
        assert resp.text == ""
        assert resp.tokens == 3


def test_openai_non_dict_choices_and_usage_do_not_crash() -> None:
    from hermia.transport.openai_compat import OpenAICompatTransport

    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"choices": "bad", "usage": "bad"}
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        resp = transport.generate("m", [{"role": "user", "content": "hi"}])
        assert resp.text == ""
        assert resp.tokens == 0


def test_ollama_non_dict_body_coerces_to_empty_response() -> None:
    """A 200 with a non-object JSON body (bare list/string/bool) must coerce to
    an empty Response, not AttributeError on the top-level ``data``."""
    from hermia.transport.ollama import OllamaTransport

    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = ["unexpected", "list", "body"]
        transport = OllamaTransport(base_url="http://localhost:11434")
        resp = transport.generate("m", [{"role": "user", "content": "hi"}])
        assert resp.text == ""
        assert resp.tokens == 0


def test_openai_non_dict_body_coerces_to_empty_response() -> None:
    from hermia.transport.openai_compat import OpenAICompatTransport

    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value.json.return_value = "unexpected-bare-string-body"
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        resp = transport.generate("m", [{"role": "user", "content": "hi"}])
        assert resp.text == ""
        assert resp.tokens == 0


# ── Finding #7 + base: in-body errors raise a typed TransportError ────────────

def test_ollama_in_body_error_raises_transport_error() -> None:
    from hermia.transport.base import TransportError
    from hermia.transport.ollama import OllamaTransport

    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"content": ""}, "error": "model not found",
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        with pytest.raises(TransportError) as exc:
            transport.generate("m", [{"role": "user", "content": "hi"}])
        assert exc.value.kind == "ollama"


def test_openai_in_body_error_raises_transport_error() -> None:
    """LiteLLM/gateways can return HTTP 200 with an {"error": ...} body and no choices."""
    from hermia.transport.base import TransportError
    from hermia.transport.openai_compat import OpenAICompatTransport

    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "error": {"message": "rate limit exceeded", "type": "rate_limit"},
        }
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        with pytest.raises(TransportError) as exc:
            transport.generate("m", [{"role": "user", "content": "hi"}])
        assert exc.value.kind == "openai-compat"


# ── Finding #8: ollama in-body error keeps the OLLAMA_ERROR: classification ──

class _OllamaErrorTransport:
    is_api_mode = False

    def generate(self, *args: object, **kwargs: object) -> Response:
        from hermia.transport.base import TransportError
        raise TransportError("model not found", kind="ollama")


def test_run_test_classifies_ollama_error_with_prefix() -> None:
    from hermia.runner import run_test

    with patch("hermia.runner.fetch_server_ps_data", return_value=dict(_PS_EMPTY)):
        result = run_test(
            "m", _BASE_TEST, _mock_sampler(), transport=_OllamaErrorTransport(),
        )
    assert result["failure_reason"].startswith("OLLAMA_ERROR")
    assert result["json_valid"] is False


# ── Finding #4: non-timeout errors record real measured elapsed, not 0.0 ─────

class _SlowFailingTransport:
    is_api_mode = False

    def generate(self, *args: object, **kwargs: object) -> Response:
        time.sleep(0.05)
        raise ValueError("connection reset")


def test_run_test_records_real_elapsed_on_non_timeout_error() -> None:
    from hermia.runner import run_test

    with patch("hermia.runner.fetch_server_ps_data", return_value=dict(_PS_EMPTY)):
        result = run_test(
            "m", _BASE_TEST, _mock_sampler(), transport=_SlowFailingTransport(),
        )
    assert result["failure_reason"].startswith("ERROR")
    assert result["elapsed_sec"] > 0, "measured wall time must be recorded on error, not 0.0"


# ── Finding #6: sampler not started/stopped in API mode (waste avoidance) ────

class _ApiTransport:
    is_api_mode = True

    def generate(self, *args: object, **kwargs: object) -> Response:
        return Response(
            text="{}", tokens=1, elapsed_sec=0.1,
            orchestration="openai-compat", orchestration_version=None, is_api_mode=True,
        )


def test_run_test_does_not_sample_in_api_mode() -> None:
    from hermia.runner import run_test

    sampler = MagicMock()
    run_test("m", _BASE_TEST, sampler, transport=_ApiTransport())
    sampler.start.assert_not_called()
    sampler.stop.assert_not_called()


# ── Finding #5: openai-compat model order is deterministic (sorted) ──────────

def test_resolve_models_openai_compat_is_sorted() -> None:
    from hermia.fleet import _resolve_models

    models, missing = _resolve_models("openai-compat", ["llama3", "alpha", "zeta"], [])
    assert [m["name"] for m in models] == ["alpha", "llama3", "zeta"]
    assert missing == set()


def test_resolve_models_ollama_preserves_order_and_reports_missing() -> None:
    from hermia.fleet import _resolve_models

    all_models = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    models, missing = _resolve_models("ollama", ["c", "a", "x"], all_models)
    assert [m["name"] for m in models] == ["a", "c"]  # preserves all_models order
    assert missing == {"x"}


# ── Finding #1 + #3: every exported column has DDL; backend fields exported ──

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _columns_created_by_ddl() -> set[str]:
    cols: set[str] = set()
    for sql_file in _SCRIPTS_DIR.glob("*.sql"):
        text = sql_file.read_text()
        # ALTER TABLE ... ADD COLUMN [IF NOT EXISTS] <name>
        for m in re.finditer(r"ADD COLUMN(?:\s+IF NOT EXISTS)?\s+(\w+)", text, re.IGNORECASE):
            cols.add(m.group(1))
        # CREATE TABLE column definitions: lines like "    <name>   TYPE,"
        if re.search(r"CREATE TABLE", text, re.IGNORECASE):
            col_def = r"\s+(\w+)\s+(TEXT|INTEGER|NUMERIC|BOOLEAN|DOUBLE|JSONB|TIMESTAMP|BIGINT)"
            for line in text.splitlines():
                m = re.match(col_def, line, re.IGNORECASE)
                if m:
                    cols.add(m.group(1))
    return cols


def test_every_pg_column_has_backing_ddl() -> None:
    from hermia.export import _PG_COLUMNS

    created = _columns_created_by_ddl()
    missing = set(_PG_COLUMNS) - created
    assert not missing, f"columns inserted but never created in scripts/*.sql: {sorted(missing)}"


def test_backend_identity_fields_are_exported() -> None:
    from hermia.export import _PG_COLUMNS

    for col in ("orchestration", "orchestration_version", "signals"):
        assert col in _PG_COLUMNS, f"{col} produced by run_test but dropped on export"


def test_build_record_serializes_signals_and_keeps_orchestration() -> None:
    from hermia.export import _build_record

    row = {
        "run_id": "r", "host": "h", "model": "m", "test_id": "t",
        "orchestration": "ollama", "orchestration_version": "0.24.0",
        "signals": {"injected_confidence_complied": True},
    }
    rec = _build_record(row)
    assert rec["orchestration"] == "ollama"
    assert rec["orchestration_version"] == "0.24.0"
    # signals must be a JSON string so psycopg2 can store it without a dict adapter
    assert rec["signals"] == json.dumps({"injected_confidence_complied": True})


# ---------------------------------------------------------------------------
# hermia_version index (PR #109 follow-up)
# ---------------------------------------------------------------------------


def test_add_backend_columns_sql_has_hermia_version_index() -> None:
    """Migration must include an active (non-commented) CREATE INDEX for hermia_version."""
    sql_file = _SCRIPTS_DIR / "add_backend_columns.sql"
    text = sql_file.read_text()
    # Strip SQL comments so a commented-out CREATE INDEX can't produce a false green.
    clean = re.sub(r"--.*$", "", text, flags=re.MULTILINE)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)
    assert re.search(
        r"CREATE\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+hermia_results\s*\(\s*hermia_version\s*\)",
        clean,
        re.IGNORECASE,
    ), "add_backend_columns.sql is missing an active CREATE INDEX for hermia_version"
