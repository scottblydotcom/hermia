"""Hermia Sink — pluggable output seam."""
from hermia.sink.anonymize import SUBMIT_WHITELIST, anonymize_row
from hermia.sink.base import Sink
from hermia.sink.local import JsonlCsvSink, PostgresSink
from hermia.sink.submission import SubmissionSink

__all__ = [
    "Sink",
    "JsonlCsvSink",
    "PostgresSink",
    "SubmissionSink",
    "SUBMIT_WHITELIST",
    "anonymize_row",
]
