"""Salt for machine_id derivation (hermia-cfqv).

FLEET-scoped by preference, per-install only as a fallback.

An earlier version salted per client install. That silently broke the thing the
identity is for: run an eval from one laptop and then from another, and the same
fleet host derives two different ids, so one machine appears as two in the
corpus. The salt has to be a property of the FLEET being measured, not of the
workstation doing the measuring.

Resolution order:
  1. ``HERMIA_FLEET_SALT`` environment variable (hex or passphrase)
  2. ``~/.hermia/fleet_salt``
  3. ``~/.hermia/machine_salt`` — per-install fallback, scope recorded as such

The scope is returned alongside the salt and must be recorded with any derived
id: two ids are only comparable when their scopes match. Silently mixing scopes
would reintroduce exactly the split-identity bug above.

Salting at all is deliberate: an UNSALTED hash of a serial or UUID is trivially
confirmable, because the candidate space is small enough to enumerate and match,
re-identifying a machine and leaking fleet composition. Note the limit, stated
plainly rather than assumed away — an adversary who obtains the salt AND holds a
candidate machine can still confirm a match. The salt raises the cost of
re-identification; it does not make it impossible.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

SALT_BYTES = 32
CONFIG_DIR = Path.home() / ".hermia"
FLEET_SALT_PATH = CONFIG_DIR / "fleet_salt"
INSTALL_SALT_PATH = CONFIG_DIR / "machine_salt"
FLEET_SALT_ENV = "HERMIA_FLEET_SALT"


@dataclass(frozen=True)
class SaltInfo:
    """A salt plus the scope it identifies machines within."""

    salt: bytes
    scope: str  # "fleet:env" | "fleet:file" | "install"


def _harden(path: Path) -> None:
    """Force owner-only permissions on a salt file.

    Applied on READ as well as write: a salt restored from a backup or copied
    between machines can already be world readable, and merely consuming it
    would leave the secret exposed indefinitely.
    """
    try:
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            path.chmod(0o600)
    except OSError:
        pass


def _read_salt(path: Path) -> bytes | None:
    try:
        raw = bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if len(raw) != SALT_BYTES:
        return None
    _harden(path)
    return raw


def _write_salt(path: Path, salt: bytes) -> None:
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


def load_salt(
    fleet_salt_path: Path | None = None, install_salt_path: Path | None = None
) -> SaltInfo:
    """Return the salt to derive machine ids with, and the scope it applies to."""
    env = os.environ.get(FLEET_SALT_ENV)
    if env and env.strip():
        raw = env.strip()
        try:
            material = bytes.fromhex(raw)
            if len(material) != SALT_BYTES:
                raise ValueError
        except ValueError:
            # Not hex — accept a passphrase, stretched to a fixed width so any
            # operator-chosen string works without a silent length surprise.
            material = hashlib.sha256(raw.encode("utf-8")).digest()
        return SaltInfo(material, "fleet:env")

    fleet_path = FLEET_SALT_PATH if fleet_salt_path is None else fleet_salt_path
    existing = _read_salt(fleet_path)
    if existing is not None:
        return SaltInfo(existing, "fleet:file")

    install_path = INSTALL_SALT_PATH if install_salt_path is None else install_salt_path
    existing = _read_salt(install_path)
    if existing is not None:
        return SaltInfo(existing, "install")

    salt = secrets.token_bytes(SALT_BYTES)
    _write_salt(install_path, salt)
    return SaltInfo(salt, "install")


def load_or_create_salt(salt_path: Path | None = None) -> bytes:
    """Backwards-compatible accessor returning only the salt bytes."""
    if salt_path is not None:
        existing = _read_salt(salt_path)
        if existing is not None:
            return existing
        salt = secrets.token_bytes(SALT_BYTES)
        _write_salt(salt_path, salt)
        return salt
    return load_salt().salt
