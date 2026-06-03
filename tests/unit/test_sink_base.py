"""Tests for the Sink protocol (runtime-checkable)."""
from __future__ import annotations

from typing import Any

from hermia.sink.base import Sink


class _ValidSink:
    def write(self, rows: list[dict[str, Any]]) -> None:
        pass


class _NoWrite:
    def other_method(self) -> None:
        pass


def test_sink_protocol_satisfied() -> None:
    assert isinstance(_ValidSink(), Sink)


def test_sink_protocol_not_satisfied() -> None:
    assert not isinstance(_NoWrite(), Sink)


def test_sink_has_write_attribute() -> None:
    assert hasattr(Sink, "write")
    assert callable(Sink.write)
