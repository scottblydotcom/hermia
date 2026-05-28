"""Hermia — LLM agentic evaluation TUI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hermia")
except PackageNotFoundError:
    __version__ = "dev"
