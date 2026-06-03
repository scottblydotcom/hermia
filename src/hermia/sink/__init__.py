"""Hermia Sink — pluggable output seam."""
from hermia.sink.base import Sink
from hermia.sink.local import JsonlCsvSink, PostgresSink

__all__ = ["Sink", "JsonlCsvSink", "PostgresSink"]
