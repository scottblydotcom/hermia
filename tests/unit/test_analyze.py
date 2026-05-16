"""Unit tests for analyze.py — Finding model, statistical detectors, CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hermia.analyze import (
    Finding,
    _detect_model_failures,
    _detect_security_critical,
    _detect_universal_weaknesses,
    _detect_worst_performers,
    _persist,
    _resolve_run_ids,
    run_analysis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(**kwargs: Any) -> Finding:
    defaults: dict[str, Any] = dict(
        finding_type="universal_weakness",
        scope="cross_model",
        models=[],
        test_ids=["some-test"],
        severity="high",
        headline="test finding",
        metric_name="behavioral_fail_pct",
        metric_value=40.0,
        run_id_refs=["run-001"],
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def _mock_cur(rows: list[tuple[Any, ...]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFinding:
    def test_content_hash_stable(self) -> None:
        f1 = _finding(models=["phi3:3.8b"], test_ids=["scope-escalation-resistance"])
        f2 = _finding(models=["phi3:3.8b"], test_ids=["scope-escalation-resistance"])
        assert f1.content_hash() == f2.content_hash()

    def test_content_hash_differs_on_models(self) -> None:
        f1 = _finding(models=["phi3:3.8b"])
        f2 = _finding(models=["mistral:7b"])
        assert f1.content_hash() != f2.content_hash()

    def test_content_hash_differs_on_metric(self) -> None:
        f1 = _finding(metric_value=40.0)
        f2 = _finding(metric_value=41.0)
        assert f1.content_hash() != f2.content_hash()

    def test_content_hash_model_order_independent(self) -> None:
        f1 = _finding(models=["a", "b", "c"])
        f2 = _finding(models=["c", "a", "b"])
        assert f1.content_hash() == f2.content_hash()

    def test_to_record_includes_hash(self) -> None:
        f = _finding()
        rec = f.to_record()
        assert "content_hash" in rec
        assert rec["content_hash"] == f.content_hash()

    def test_to_record_all_fields_present(self) -> None:
        f = _finding()
        rec = f.to_record()
        for field in ("finding_type", "scope", "models", "test_ids", "severity",
                      "headline", "metric_name", "metric_value", "source",
                      "run_id_refs", "tags", "notes", "observed_at"):
            assert field in rec

    def test_default_source_is_statistical(self) -> None:
        f = _finding()
        assert f.source == "statistical"

    def test_custom_source(self) -> None:
        f = _finding(source="llm-manual")
        assert f.source == "llm-manual"

    def test_hash_length(self) -> None:
        assert len(_finding().content_hash()) == 32


# ---------------------------------------------------------------------------
# _detect_universal_weaknesses
# ---------------------------------------------------------------------------

class TestDetectUniversalWeaknesses:
    def test_returns_finding_for_weak_test(self) -> None:
        cur = _mock_cur([("some-test", 10, 7, 45.0)])
        findings = _detect_universal_weaknesses(cur, ["run-001"])
        assert len(findings) == 1
        f = findings[0]
        assert f.finding_type == "universal_weakness"
        assert f.test_ids == ["some-test"]
        assert f.metric_value == 45.0

    def test_severity_critical_above_50(self) -> None:
        cur = _mock_cur([("t", 5, 4, 55.0)])
        findings = _detect_universal_weaknesses(cur, ["r"])
        assert findings[0].severity == "critical"

    def test_severity_high_between_35_and_50(self) -> None:
        cur = _mock_cur([("t", 5, 4, 40.0)])
        findings = _detect_universal_weaknesses(cur, ["r"])
        assert findings[0].severity == "high"

    def test_severity_medium_below_35(self) -> None:
        cur = _mock_cur([("t", 5, 4, 32.0)])
        findings = _detect_universal_weaknesses(cur, ["r"])
        assert findings[0].severity == "medium"

    def test_empty_rows_returns_no_findings(self) -> None:
        cur = _mock_cur([])
        assert _detect_universal_weaknesses(cur, ["r"]) == []

    def test_models_list_is_empty_cross_model(self) -> None:
        cur = _mock_cur([("t", 8, 5, 38.0)])
        f = _detect_universal_weaknesses(cur, ["r"])[0]
        assert f.models == []
        assert f.scope == "cross_model"

    def test_supporting_sql_stored(self) -> None:
        cur = _mock_cur([("t", 5, 4, 40.0)])
        f = _detect_universal_weaknesses(cur, ["r"])[0]
        assert len(f.supporting_sql) > 0

    def test_run_ids_propagated(self) -> None:
        cur = _mock_cur([("t", 5, 4, 40.0)])
        run_ids = ["run-001", "run-002"]
        f = _detect_universal_weaknesses(cur, run_ids)[0]
        assert f.run_id_refs == run_ids


# ---------------------------------------------------------------------------
# _detect_model_failures
# ---------------------------------------------------------------------------

class TestDetectModelFailures:
    def test_returns_finding_for_failing_model(self) -> None:
        cur = _mock_cur([("phi3:3.8b", "scope-escalation-resistance", 100.0, 20.0)])
        findings = _detect_model_failures(cur, ["run-001"])
        assert len(findings) == 1
        f = findings[0]
        assert f.finding_type == "model_failure"
        assert f.models == ["phi3:3.8b"]
        assert f.test_ids == ["scope-escalation-resistance"]
        assert f.metric_value == 100.0
        assert f.baseline_value == 20.0

    def test_severity_high_above_70(self) -> None:
        cur = _mock_cur([("m", "t", 75.0, 15.0)])
        f = _detect_model_failures(cur, ["r"])[0]
        assert f.severity == "high"

    def test_severity_medium_below_70(self) -> None:
        cur = _mock_cur([("m", "t", 50.0, 15.0)])
        f = _detect_model_failures(cur, ["r"])[0]
        assert f.severity == "medium"

    def test_empty_returns_no_findings(self) -> None:
        cur = _mock_cur([])
        assert _detect_model_failures(cur, ["r"]) == []

    def test_scope_is_model_specific(self) -> None:
        cur = _mock_cur([("m", "t", 50.0, 10.0)])
        f = _detect_model_failures(cur, ["r"])[0]
        assert f.scope == "model_specific"

    def test_multiple_rows_produce_multiple_findings(self) -> None:
        cur = _mock_cur([
            ("phi3:3.8b", "scope-escalation-resistance", 100.0, 20.0),
            ("mistral:7b", "adversarial-input-signal-in-noise", 80.0, 25.0),
        ])
        findings = _detect_model_failures(cur, ["r"])
        assert len(findings) == 2


# ---------------------------------------------------------------------------
# _detect_security_critical
# ---------------------------------------------------------------------------

class TestDetectSecurityCritical:
    def test_returns_finding_for_bypass(self) -> None:
        cur = _mock_cur([
            ("model accepted user-turn policy override",
             ["qwen3:8b", "mistral:7b"], ["system-user-precedence"], 5)
        ])
        findings = _detect_security_critical(cur, ["run-001"])
        assert len(findings) == 1
        f = findings[0]
        assert f.finding_type == "security_critical"
        assert f.severity == "critical"
        assert "qwen3:8b" in f.models
        assert f.metric_value == 5.0

    def test_empty_returns_no_findings(self) -> None:
        cur = _mock_cur([])
        assert _detect_security_critical(cur, ["r"]) == []

    def test_tags_include_security(self) -> None:
        cur = _mock_cur([("model executed the injection", ["phi3:3.8b"], ["t"], 4)])
        f = _detect_security_critical(cur, ["r"])[0]
        assert "security" in f.tags

    def test_headline_truncates_long_reason(self) -> None:
        long_reason = "x" * 200
        cur = _mock_cur([(long_reason, ["m"], ["t"], 1)])
        f = _detect_security_critical(cur, ["r"])[0]
        assert len(f.headline) < 200


# ---------------------------------------------------------------------------
# _detect_worst_performers
# ---------------------------------------------------------------------------

class TestDetectWorstPerformers:
    def test_returns_finding_per_model(self) -> None:
        cur = _mock_cur([
            ("phi3:3.8b", 10, 100, 10.0),
            ("mistral:7b", 30, 100, 30.0),
            ("llama3:8b", 25, 100, 25.0),
        ])
        findings = _detect_worst_performers(cur, ["run-001"])
        assert len(findings) == 3

    def test_severity_high_below_40(self) -> None:
        cur = _mock_cur([("phi3:3.8b", 10, 100, 10.0)])
        f = _detect_worst_performers(cur, ["r"])[0]
        assert f.severity == "high"

    def test_severity_medium_above_40(self) -> None:
        cur = _mock_cur([("m", 45, 100, 45.0)])
        f = _detect_worst_performers(cur, ["r"])[0]
        assert f.severity == "medium"

    def test_finding_type(self) -> None:
        cur = _mock_cur([("m", 10, 100, 10.0)])
        f = _detect_worst_performers(cur, ["r"])[0]
        assert f.finding_type == "worst_performer"

    def test_empty_returns_no_findings(self) -> None:
        cur = _mock_cur([])
        assert _detect_worst_performers(cur, ["r"]) == []


# ---------------------------------------------------------------------------
# _resolve_run_ids
# ---------------------------------------------------------------------------

class TestResolveRunIds:
    def test_explicit_run_id_returned_directly(self) -> None:
        cur = MagicMock()
        result = _resolve_run_ids(cur, "run-999", last_n=5)
        assert result == ["run-999"]
        cur.execute.assert_not_called()

    def test_queries_latest_when_no_run_id(self) -> None:
        cur = _mock_cur([("run-003",), ("run-002",), ("run-001",)])
        result = _resolve_run_ids(cur, None, last_n=3)
        assert result == ["run-003", "run-002", "run-001"]
        cur.execute.assert_called_once()

    def test_empty_db_returns_empty_list(self) -> None:
        cur = _mock_cur([])
        assert _resolve_run_ids(cur, None, last_n=5) == []


# ---------------------------------------------------------------------------
# _persist
# ---------------------------------------------------------------------------

class TestPersist:
    def test_dry_run_prints_without_writing(self, capsys: pytest.CaptureFixture[str]) -> None:
        findings = [_finding(headline="dry run test")]
        _persist(findings, dsn="unused", export_path=None, dry_run=True)
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "dry run test" in out

    def test_empty_findings_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = _persist([], dsn="unused", export_path=None, dry_run=False)
        assert result == 0

    def test_missing_psycopg2_exits(self) -> None:
        findings = [_finding()]
        with patch.dict(sys.modules, {"psycopg2": None}):
            with pytest.raises(SystemExit):
                _persist(findings, dsn="postgresql://fake/db", export_path=None, dry_run=False)

    def test_jsonl_export_appends(self, tmp_path: Path) -> None:
        findings = [_finding(headline="exported")]
        export_file = tmp_path / "findings.jsonl"

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 1
        mock_conn.cursor.return_value = mock_cur

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2,
                                       "psycopg2.extras": mock_psycopg2.extras}):
            _persist(findings, dsn="postgresql://fake/db", export_path=export_file, dry_run=False)

        assert export_file.exists()
        lines = export_file.read_text().strip().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["headline"] == "exported"

    def test_jsonl_append_does_not_overwrite(self, tmp_path: Path) -> None:
        export_file = tmp_path / "findings.jsonl"
        export_file.write_text('{"existing": true}\n')

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 1
        mock_conn.cursor.return_value = mock_cur

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2,
                                       "psycopg2.extras": mock_psycopg2.extras}):
            _persist([_finding()], dsn="postgresql://fake/db",
                     export_path=export_file, dry_run=False)

        lines = export_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"existing": True}


# ---------------------------------------------------------------------------
# CLI — main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_dsn_exits(self) -> None:
        with patch("sys.argv", ["hermia-analyze"]):
            with patch.dict("os.environ", {}, clear=True):
                from hermia.analyze import main
                with pytest.raises(SystemExit):
                    main()

    def _make_mock_pg(self, run_ids: list[tuple[str, ...]]) -> MagicMock:
        """Build a psycopg2 mock whose cursor returns run_ids on the first fetchall,
        then empty lists for all subsequent detector calls."""
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.side_effect = [run_ids] + [[]] * 10
        mock_conn.cursor.return_value = mock_cur
        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        return mock_psycopg2

    def test_dry_run_does_not_require_dsn(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_psycopg2 = self._make_mock_pg([("run-001",)])
        with patch("sys.argv", ["hermia-analyze", "--dsn", "postgresql://fake/db", "--dry-run"]):
            with patch.dict(sys.modules, {"psycopg2": mock_psycopg2,
                                           "psycopg2.extras": mock_psycopg2.extras}):
                from hermia.analyze import main
                main()  # should not raise

    def test_dsn_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMIA_PG_DSN", "postgresql://env/db")
        mock_psycopg2 = self._make_mock_pg([])
        with patch("sys.argv", ["hermia-analyze", "--dry-run"]):
            with patch.dict(sys.modules, {"psycopg2": mock_psycopg2,
                                           "psycopg2.extras": mock_psycopg2.extras}):
                from hermia.analyze import main
                main()
