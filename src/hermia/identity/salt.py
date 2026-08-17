"""Per-install salt for machine_id derivation (hermia-cfqv).

Stored in its OWN file, deliberately NOT in ``~/.hermia/config.toml``: that file
is written with a whole-file overwrite by ``submit.load_or_create_install_id``,
so a salt stored beside ``install_id`` would be silently destroyed the first
time the install id is regenerated.

The salt is what makes ``machine_id`` locally unique but globally meaningless.
An UNSALTED hash of platform-uuid + cpu + ram is trivially confirmable: the
candidate space is small enough that anyone holding a machine can hash it and
confirm a match, re-identifying the box and leaking fleet composition. The
tradeoff, stated explicitly: cross-install comparison becomes impossible. That
is acceptable — the requirement is identifying machines WITHIN one fleet's data.
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

SALT_BYTES = 32
DEFAULT_SALT_PATH = Path.home() / ".hermia" / "machine_salt"


def load_or_create_salt(salt_path: Path | None = None) -> bytes:
    """Return the per-install salt, creating and persisting it if absent.

    A missing, unreadable, malformed, or wrong-length file is regenerated. An
    unwritable location yields an ephemeral salt for this process rather than
    raising — the CLI keeps working, though ``machine_id`` will not then be
    stable across runs.
    """
    path = DEFAULT_SALT_PATH if salt_path is None else salt_path
    try:
        raw = bytes.fromhex(path.read_text(encoding="utf-8").strip())
        if len(raw) == SALT_BYTES:
            _harden(path)
            return raw
    except (OSError, ValueError):
        pass  # absent, unreadable, or not hex — regenerate below

    salt = secrets.token_bytes(SALT_BYTES)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create with 0600 ALREADY SET rather than write-then-chmod: under a
        # normal 022 umask the latter leaves the secret readable by every local
        # process for the window between the two calls.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, salt.hex().encode("ascii"))
        finally:
            os.close(fd)
        _harden(path)
    except OSError:
        pass  # read-only home: ephemeral for this process, do not crash
    return salt


def _harden(path: Path) -> None:
    """Force owner-only permissions on an existing salt file.

    Applied on READ as well as write: a salt restored from a backup, copied
    between machines, or written by an older build can already be world
    readable, and simply consuming it would leave the secret exposed forever.
    """
    try:
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            path.chmod(0o600)
    except OSError:
        pass
