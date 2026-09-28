"""Tests for git-sha provenance stamping (hermia-c38b).

__version__ reads frozen editable-install dist-info metadata, which goes
stale the moment a checkout moves without a reinstall. __git_sha__ is
stamped independently, computed fresh from the actual checkout, so stale
version data is self-diagnosing.
"""
import subprocess

from hermia import _detect_git_sha


def test_detect_git_sha_returns_nonempty_string() -> None:
    sha = _detect_git_sha()
    assert isinstance(sha, str)
    assert sha


def test_detect_git_sha_falls_back_to_unknown_when_git_missing(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert _detect_git_sha() == "unknown"


def test_detect_git_sha_falls_back_to_unknown_on_non_git_checkout(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert _detect_git_sha() == "unknown"


def test_detect_git_sha_falls_back_to_unknown_when_file_untracked_in_enclosing_repo(
    monkeypatch,
) -> None:
    """git rev-parse searches upward for the nearest .git — if the package
    happens to sit inside an unrelated enclosing repo (e.g. a venv nested
    inside a stale checkout), that repo's HEAD must not be reported as
    hermia's git_sha."""

    def _fake_run(cmd, **kwargs):
        if "ls-files" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="deadbeef\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert _detect_git_sha() == "unknown"
