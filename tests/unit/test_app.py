"""Unit tests for app.py — CLI argument parsing and dispatch."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermia.app import _positive_int

# ---------------------------------------------------------------------------
# _positive_int
# ---------------------------------------------------------------------------


def test_positive_int_valid() -> None:
    assert _positive_int("1") == 1
    assert _positive_int("10") == 10


def test_positive_int_zero_raises() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match=">="):
        _positive_int("0")


def test_positive_int_negative_raises() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_int("-5")


# ---------------------------------------------------------------------------
# main() — --audit path
# ---------------------------------------------------------------------------


def test_main_audit_missing_source_exits_1(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["hermia", "--audit", str(tmp_path / "missing")])
    with pytest.raises(SystemExit) as exc:
        from hermia.app import main
        main()
    assert exc.value.code == 1


def test_main_audit_jsonl_existing_file(tmp_path: Path, monkeypatch, capsys) -> None:
    """--audit FILE --audit-format jsonl should call run_audit and exit 0."""
    results_file = tmp_path / "eval_001.jsonl"
    results_file.write_text(json.dumps({"model": "x", "test_id": "t"}) + "\n")

    monkeypatch.setattr(
        sys, "argv",
        ["hermia", "--audit", str(results_file), "--audit-format", "jsonl"],
    )

    mock_run_audit = MagicMock()
    with (
        patch("hermia.audit.run_audit", mock_run_audit),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    mock_run_audit.assert_called_once()


def test_main_audit_html_tty_writes_dated_file(tmp_path: Path, monkeypatch, capsys) -> None:
    """--audit-format html with a TTY should auto-name the output file."""
    results_file = tmp_path / "eval_001.jsonl"
    results_file.write_text(json.dumps({"model": "x"}) + "\n")

    monkeypatch.setattr(
        sys, "argv",
        ["hermia", "--audit", str(results_file), "--audit-format", "html"],
    )
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    mock_run_audit = MagicMock()
    with (
        patch("hermia.audit.run_audit", mock_run_audit),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    mock_run_audit.assert_called_once()
    # output kwarg should be a Path (not None) when writing to a dated file
    output_arg = mock_run_audit.call_args.kwargs.get("output")
    assert output_arg is not None
    assert str(output_arg).startswith("hermia-audit-")


def test_main_audit_html_non_tty_no_file(tmp_path: Path, monkeypatch) -> None:
    """--audit-format html without a TTY should pass output=None."""
    results_file = tmp_path / "eval_001.jsonl"
    results_file.write_text(json.dumps({"model": "x"}) + "\n")

    monkeypatch.setattr(
        sys, "argv",
        ["hermia", "--audit", str(results_file), "--audit-format", "html"],
    )
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    mock_run_audit = MagicMock()
    with (
        patch("hermia.audit.run_audit", mock_run_audit),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    output_arg = mock_run_audit.call_args.kwargs.get("output")
    assert output_arg is None


# ---------------------------------------------------------------------------
# main() — --fleet path
# ---------------------------------------------------------------------------


def test_main_fleet_valid_config(tmp_path: Path, monkeypatch) -> None:
    fleet_file = tmp_path / "fleet.yaml"
    fleet_file.write_text("hosts:\n  - name: local\n    host: http://localhost:11434\n")

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(fleet_file)])

    mock_load = MagicMock(return_value=[{"name": "local", "host": "http://localhost:11434"}])
    mock_run = MagicMock()

    with (
        patch("hermia.fleet.load_fleet_config", mock_load),
        patch("hermia.fleet.run_fleet", mock_run),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 0
    mock_run.assert_called_once()


def test_main_fleet_error_exits_1(tmp_path: Path, monkeypatch, capsys) -> None:
    fleet_file = tmp_path / "fleet.yaml"
    fleet_file.write_text("hosts: []\n")

    monkeypatch.setattr(sys, "argv", ["hermia", "--fleet", str(fleet_file)])

    mock_load = MagicMock(side_effect=ValueError("bad config"))
    with (
        patch("hermia.fleet.load_fleet_config", mock_load),
        pytest.raises(SystemExit) as exc,
    ):
        from hermia.app import main
        main()

    assert exc.value.code == 1
    assert "hermia:" in capsys.readouterr().err
