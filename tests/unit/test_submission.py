"""Tests for SubmissionSink — opt-in anonymized POST with dry-run."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from hermia.sink.submission import SubmissionSink

# ---------------------------------------------------------------------------
# Dry-run mode — no network call
# ---------------------------------------------------------------------------


def test_dry_run_no_endpoint_no_network_call(capsys: pytest.CaptureFixture[str]) -> None:
    """endpoint=None with any dry_run value must never call requests.post."""
    rows = [{"host": "example.com", "raw_response": "raw text", "model": "m"}]
    with patch("requests.post") as mock_post:
        SubmissionSink(endpoint=None, dry_run=True).write(rows)
    mock_post.assert_not_called()


def test_dry_run_true_with_endpoint_no_network_call() -> None:
    """dry_run=True must never call requests.post even when endpoint is set."""
    rows = [{"host": "example.com", "raw_response": "raw text", "model": "m"}]
    with patch("requests.post") as mock_post:
        SubmissionSink(endpoint="https://example.test/submit", dry_run=True).write(rows)
    mock_post.assert_not_called()


def test_dry_run_output_contains_anonymized_rows(capsys: pytest.CaptureFixture[str]) -> None:
    """Dry-run should print the anonymized payload to stdout."""
    rows = [{"model": "qwen2.5:32b", "tokens": 42, "host": "private-host"}]
    SubmissionSink(endpoint=None, dry_run=True).write(rows)
    captured = capsys.readouterr().out
    assert "qwen2.5:32b" in captured  # whitelisted field present
    assert "private-host" not in captured  # host must NOT appear


# ---------------------------------------------------------------------------
# Live mode — posts anonymized payload
# ---------------------------------------------------------------------------


def test_live_posts_anonymized_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live mode POSTs the anonymized payload to the endpoint."""
    rows = [{"host": "example.com", "raw_response": "raw text", "model": "m", "tokens": 5}]
    monkeypatch.setenv("TEST_SUBMIT_MARKER", "marker-value-abc")

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("requests.post", return_value=mock_response) as mock_post:
        SubmissionSink(
            endpoint="https://example.test/submit",
            token_env="TEST_SUBMIT_MARKER",  # noqa: S106
            dry_run=False,
        ).write(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.test/submit"
    assert "json" in kwargs
    payload = kwargs["json"]
    assert isinstance(payload, list)
    assert len(payload) == 1
    row = payload[0]
    # Whitelisted field passes through
    assert row.get("model") == "m"
    assert row.get("tokens") == 5
    # Forbidden fields are stripped
    assert "host" not in row
    assert "raw_response" not in row


def test_live_authorization_header_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth header must be built from the env var value."""
    marker = "bearer-marker-xyz789"
    monkeypatch.setenv("MY_MARKER_ENV", marker)
    rows = [{"model": "m"}]

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("requests.post", return_value=mock_response) as mock_post:
        SubmissionSink(
            endpoint="https://example.test/submit",
            token_env="MY_MARKER_ENV",  # noqa: S106
            dry_run=False,
        ).write(rows)

    _, kwargs = mock_post.call_args
    headers = kwargs.get("headers", {})
    assert headers.get("Authorization") == f"Bearer {marker}"


def test_live_non_2xx_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-2xx response must not raise; a warning should be logged."""
    monkeypatch.setenv("TEST_SUBMIT_MARKER", "marker-value-abc")
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.ok = False

    with (
        patch("requests.post", return_value=mock_response),
        patch("hermia.sink.submission.logger") as mock_logger,
    ):
        # Must not raise
        SubmissionSink(
            endpoint="https://example.test/submit",
            token_env="TEST_SUBMIT_MARKER",  # noqa: S106
            dry_run=False,
        ).write([{"model": "m"}])

    mock_logger.warning.assert_called()


def test_live_request_exception_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Network errors must be caught and logged, not raised."""
    monkeypatch.setenv("TEST_SUBMIT_MARKER", "marker-value-abc")

    with (
        patch("requests.post", side_effect=requests.exceptions.RequestException("timeout")),
        patch("hermia.sink.submission.logger") as mock_logger,
    ):
        # Must not raise
        SubmissionSink(
            endpoint="https://example.test/submit",
            token_env="TEST_SUBMIT_MARKER",  # noqa: S106
            dry_run=False,
        ).write([{"model": "m"}])

    mock_logger.warning.assert_called()


# ---------------------------------------------------------------------------
# Privacy guard — sentinel value must never appear in the POST body
# ---------------------------------------------------------------------------


def test_privacy_guard_sentinel_not_in_post_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forbidden field values must not appear in the JSON body posted to the server."""
    sentinel = "SENTINEL_XZQJ_abc123"
    rows = [
        {
            "host": sentinel,
            "raw_response": sentinel,
            "output_preview": sentinel,
            "model": "m",
            "tokens": 1,
        }
    ]
    monkeypatch.setenv("TEST_SUBMIT_MARKER", "marker-value-abc")
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("requests.post", return_value=mock_response) as mock_post:
        SubmissionSink(
            endpoint="https://example.test/submit",
            token_env="TEST_SUBMIT_MARKER",  # noqa: S106
            dry_run=False,
        ).write(rows)

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    payload_str = json.dumps(kwargs["json"])
    assert sentinel not in payload_str, (
        "Privacy violation: sentinel value appeared in POST body"
    )
