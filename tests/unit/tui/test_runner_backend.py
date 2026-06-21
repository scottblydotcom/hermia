"""Tests for hermia.tui.runner_backend — TuiRunner + helpers."""
import asyncio

import pytest

from hermia.tui.runner_backend import verdict_from_result


class TestVerdictFromResult:
    def test_empty_failure_reason_is_defended(self) -> None:
        result = {"failure_reason": "", "signals": {}}
        assert verdict_from_result(result) == "defended"

    def test_timeout_failure_is_error(self) -> None:
        result = {"failure_reason": "TIMEOUT: no response in 90s", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_schema_fail_is_error(self) -> None:
        result = {"failure_reason": "SCHEMA_FAIL", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_empty_response_is_error(self) -> None:
        result = {"failure_reason": "EMPTY_RESPONSE", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_api_error_is_error(self) -> None:
        result = {"failure_reason": "API_ERROR: connection refused", "signals": {}}
        assert verdict_from_result(result) == "error"

    def test_missing_failure_reason_key_treated_as_defended(self) -> None:
        result = {"signals": {}}
        assert verdict_from_result(result) == "defended"
