"""Tests for --submit / --submit-dry-run CLI flags in app.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_fleet_file(tmp_path: Path) -> Path:
    f = tmp_path / "fleet.yaml"
    f.write_text("hosts:\n  - name: local\n    host: http://localhost:11434\n")
    return f


def _make_jsonl(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    p = tmp_path / "eval.jsonl"
    with p.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


# ---------------------------------------------------------------------------
# --submit-dry-run
# ---------------------------------------------------------------------------


def test_submit_dry_run_calls_submission_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--submit-dry-run must construct a dry-run SubmissionSink and call .write."""
    fleet_file = _make_fleet_file(tmp_path)
    rows = [{"model": "m", "score": 1.0}]
    jsonl_path = _make_jsonl(tmp_path, rows)

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(fleet_file), "--submit-dry-run"])

    mock_load = MagicMock(return_value=[{"name": "local", "host": "http://localhost:11434"}])
    mock_run = MagicMock(return_value=jsonl_path)
    mock_sink_instance = MagicMock()
    mock_sink_class = MagicMock(return_value=mock_sink_instance)

    with (
        patch("hermia.fleet.load_fleet_config", mock_load),
        patch("hermia.fleet.run_fleet", mock_run),
        patch("hermia.sink.submission.SubmissionSink", mock_sink_class),
        patch("requests.post") as mock_post,
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    mock_run.assert_called_once()
    # Must construct a dry-run sink (no endpoint)
    mock_sink_class.assert_called_once_with(endpoint=None, dry_run=True)
    # Must call write with the loaded rows
    mock_sink_instance.write.assert_called_once_with(rows)
    # No network call
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# --submit
# ---------------------------------------------------------------------------


def test_submit_live_calls_submission_sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--submit must construct a live SubmissionSink with endpoint from env."""
    fleet_file = _make_fleet_file(tmp_path)
    rows = [{"model": "m", "score": 1.0}]
    jsonl_path = _make_jsonl(tmp_path, rows)
    submit_url = "https://example.test/submit"

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(fleet_file), "--submit"])
    monkeypatch.setenv("HERMIA_SUBMIT_URL", submit_url)

    mock_load = MagicMock(return_value=[{"name": "local", "host": "http://localhost:11434"}])
    mock_run = MagicMock(return_value=jsonl_path)
    mock_sink_instance = MagicMock()
    mock_sink_class = MagicMock(return_value=mock_sink_instance)

    with (
        patch("hermia.fleet.load_fleet_config", mock_load),
        patch("hermia.fleet.run_fleet", mock_run),
        patch("hermia.sink.submission.SubmissionSink", mock_sink_class),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    mock_run.assert_called_once()
    mock_sink_class.assert_called_once_with(
        endpoint=submit_url,
        token_env="HERMIA_SUBMIT_TOKEN",  # noqa: S106
        dry_run=False,
    )
    mock_sink_instance.write.assert_called_once_with(rows)


# ---------------------------------------------------------------------------
# No flags — no SubmissionSink
# ---------------------------------------------------------------------------


def test_no_submit_flags_no_submission_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --submit or --submit-dry-run, SubmissionSink must not be created."""
    fleet_file = _make_fleet_file(tmp_path)
    jsonl_path = tmp_path / "eval.jsonl"
    jsonl_path.write_text("")  # empty but exists

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(fleet_file)])

    mock_load = MagicMock(return_value=[{"name": "local", "host": "http://localhost:11434"}])
    mock_run = MagicMock(return_value=jsonl_path)
    mock_sink_class = MagicMock()

    with (
        patch("hermia.fleet.load_fleet_config", mock_load),
        patch("hermia.fleet.run_fleet", mock_run),
        patch("hermia.sink.submission.SubmissionSink", mock_sink_class),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    mock_sink_class.assert_not_called()
