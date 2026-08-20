"""The TUI must WARN (not silently drop) an identity block it cannot yet honor."""
import pytest

from hermia.tui.fleet_io import _headless_host


def test_headless_host_warns_on_identity_block():
    entry = {"name": "n", "host": "http://h:11434", "identity": {"transport": "ssh", "ssh": "g"}}
    with pytest.warns(UserWarning, match="does not yet stamp machine identity"):
        _headless_host(entry)


def test_headless_host_no_warning_without_identity(recwarn):
    _headless_host({"name": "n", "host": "http://h:11434"})
    assert len(recwarn) == 0
