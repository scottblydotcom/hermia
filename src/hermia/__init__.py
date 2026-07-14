"""Hermia — LLM agentic evaluation TUI."""

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    __version__ = version("hermia")
except PackageNotFoundError:
    __version__ = "dev"


def _detect_git_sha() -> str:
    """Short git commit SHA of the running checkout, or "unknown" if unavailable.

    __version__ reads frozen editable-install dist-info metadata, which goes
    stale the moment a checkout moves to a different commit without a
    reinstall (see hermia-c38b). __git_sha__ is computed independently and
    freshly on every import, so stale __version__ data is self-diagnosing.
    """
    try:
        file_path = str(Path(__file__).resolve())
        pkg_dir = str(Path(__file__).resolve().parent)
        # git rev-parse searches upward for the nearest .git — if this file
        # sits inside an unrelated enclosing repo (e.g. a venv nested inside
        # a stale checkout), that repo's HEAD would be reported instead.
        # Confirm the file is actually tracked here before trusting HEAD.
        subprocess.run(
            ["git", "-C", pkg_dir, "ls-files", "--error-unmatch", file_path],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        result = subprocess.run(
            ["git", "-C", pkg_dir, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


__git_sha__ = _detect_git_sha()
