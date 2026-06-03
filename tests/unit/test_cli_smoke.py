"""CLI subprocess smoke tests for Hermia entrypoints.

Complements test_app.py which uses in-process mocking for hermia (app.py:main).
This module adds subprocess smoke coverage for the entrypoints that lack it:
- hermia (app.py:main) — --help and --version via python -m hermia.app
- hermia-regression (regression.py:main) — --help and --version
- hermia-push (export.py:main) — --help and --version
- hermia-analyze (analyze.py:main) — --help and --version

All invocations use `python -c "..."` or `python -m <module>` so the tests work
in CI without the console scripts on PATH (just `pip install -e .` is enough).
"""

from __future__ import annotations

import subprocess
import sys

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True)


def _pycall(entrypoint: str, module: str, func: str, flag: str) -> subprocess.CompletedProcess[str]:
    """Invoke `from module import func` with sys.argv=[entrypoint, flag]."""
    cmd = (
        f"import sys; sys.argv=['{entrypoint}','{flag}']; "
        f"from {module} import {func}; {func}()"
    )
    return _run([sys.executable, "-c", cmd])


# ---------------------------------------------------------------------------
# hermia (app.py) — via python -m hermia.app
# test_app.py already covers --version in-process; here we add subprocess coverage
# ---------------------------------------------------------------------------


def test_hermia_help_subprocess() -> None:
    r = _run([sys.executable, "-m", "hermia.app", "--help"])
    assert r.returncode == 0, f"hermia --help exited {r.returncode}: {r.stderr}"
    assert r.stdout.strip(), "hermia --help produced no output"
    assert "usage" in r.stdout.lower()


def test_hermia_version_subprocess() -> None:
    r = _run([sys.executable, "-m", "hermia.app", "--version"])
    assert r.returncode == 0, f"hermia --version exited {r.returncode}: {r.stderr}"
    combined = r.stdout + r.stderr
    assert combined.strip(), "hermia --version produced no output"


# ---------------------------------------------------------------------------
# hermia-regression
# ---------------------------------------------------------------------------


def test_hermia_regression_help() -> None:
    r = _pycall("hermia-regression", "hermia.regression", "main", "--help")
    assert r.returncode == 0, f"hermia-regression --help exited {r.returncode}: {r.stderr}"
    assert r.stdout.strip(), "hermia-regression --help produced no output"
    assert "usage" in r.stdout.lower()


def test_hermia_regression_version() -> None:
    r = _pycall("hermia-regression", "hermia.regression", "main", "--version")
    assert r.returncode == 0, f"hermia-regression --version exited {r.returncode}: {r.stderr}"
    combined = r.stdout + r.stderr
    assert combined.strip(), "hermia-regression --version produced no output"


# ---------------------------------------------------------------------------
# hermia-push (export.py)
# ---------------------------------------------------------------------------


def test_hermia_push_help() -> None:
    r = _pycall("hermia-push", "hermia.export", "main", "--help")
    assert r.returncode == 0, f"hermia-push --help exited {r.returncode}: {r.stderr}"
    assert r.stdout.strip(), "hermia-push --help produced no output"
    assert "usage" in r.stdout.lower()


def test_hermia_push_version() -> None:
    r = _pycall("hermia-push", "hermia.export", "main", "--version")
    assert r.returncode == 0, f"hermia-push --version exited {r.returncode}: {r.stderr}"
    combined = r.stdout + r.stderr
    assert combined.strip(), "hermia-push --version produced no output"


# ---------------------------------------------------------------------------
# hermia-analyze
# ---------------------------------------------------------------------------


def test_hermia_analyze_help() -> None:
    r = _pycall("hermia-analyze", "hermia.analyze", "main", "--help")
    assert r.returncode == 0, f"hermia-analyze --help exited {r.returncode}: {r.stderr}"
    assert r.stdout.strip(), "hermia-analyze --help produced no output"
    assert "usage" in r.stdout.lower()


def test_hermia_analyze_version() -> None:
    r = _pycall("hermia-analyze", "hermia.analyze", "main", "--version")
    assert r.returncode == 0, f"hermia-analyze --version exited {r.returncode}: {r.stderr}"
    combined = r.stdout + r.stderr
    assert combined.strip(), "hermia-analyze --version produced no output"
