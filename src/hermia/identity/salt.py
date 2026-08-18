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
import threading
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
    scope: str  # "fleet:env" | "fleet:file" | "install" | "ephemeral"

    @property
    def is_stable(self) -> bool:
        """False when the salt could not be persisted, so ids change each run."""
        return self.scope != "ephemeral"


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


def _write_salt(path: Path, salt: bytes) -> tuple[bytes, bool]:
    """Create the salt file exclusively; return whichever salt actually won.

    Two processes starting for the first time together would otherwise each mint
    a salt and the second would overwrite the first, so ids derived either side
    of that moment would silently disagree.

    Write-then-link, not create-then-write: creating the destination with O_EXCL
    and filling it afterwards still leaves a window where the losing racer opens
    a file that exists but is EMPTY, reads nothing usable, and falls back to its
    own salt — the very divergence this is meant to stop. Building the content
    in a private temp file and linking it into place makes the destination
    appear only once it is complete. os.link fails if the target exists, so the
    first linker wins and everyone else reads the winner's value.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create with 0600 ALREADY SET rather than write-then-chmod: under a
        # normal 022 umask the latter leaves the secret readable by every local
        # process for the window between the two calls.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, salt.hex().encode("ascii"))
        finally:
            os.close(fd)
    except OSError:
        return salt, False  # read-only home: ephemeral, but SAY so

    try:
        try:
            os.link(tmp, path)
        except OSError as exc:
            if isinstance(exc, FileExistsError):
                raise
            # Filesystem without hard links (exFAT, some network and container
            # mounts). Fall back to an EXCLUSIVE create, never os.replace:
            # replace is an unconditional overwrite, so two first-run processes
            # would each install their own salt and every id derived either
            # side of that moment would disagree.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, salt.hex().encode("ascii"))
            finally:
                os.close(fd)
        _harden(path)
        return salt, True
    except FileExistsError:
        existing = _read_salt(path)
        if existing is not None:
            return existing, True
        # The file exists but is EMPTY or malformed — a process killed
        # mid-write, or a truncated restore. Left alone it is never repaired,
        # so every future run mints a throwaway salt and the machine gets a
        # brand new id every single time, silently and forever. Overwriting is
        # correct here precisely because nothing usable is being destroyed.
        try:
            os.replace(tmp, path)
            _harden(path)
        except OSError:
            return salt, False
        return salt, True
    except OSError:
        return salt, False
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


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
            # Not hex — accept a passphrase, stretched with a deliberately slow
            # KDF. A single SHA-256 is far too cheap here: an operator-chosen
            # phrase has low entropy, so a plain digest can be brute-forced to
            # recover the salt, and recovering the salt is what makes derived
            # ids confirmable against candidate hardware. The context string is
            # fixed, not random, because every workstation must derive the SAME
            # material from the same phrase — that is the entire point of a
            # fleet-scoped salt.
            material = hashlib.scrypt(
                raw.encode("utf-8"),
                salt=b"hermia-fleet-salt-v1",
                n=2**14, r=8, p=1, dklen=SALT_BYTES,
            )
        return SaltInfo(material, "fleet:env")

    fleet_path = FLEET_SALT_PATH if fleet_salt_path is None else fleet_salt_path
    existing = _read_salt(fleet_path)
    if existing is not None:
        return SaltInfo(existing, "fleet:file")

    install_path = INSTALL_SALT_PATH if install_salt_path is None else install_salt_path
    existing = _read_salt(install_path)
    if existing is not None:
        return SaltInfo(existing, "install")

    salt, persisted = _write_salt(install_path, secrets.token_bytes(SALT_BYTES))
    # A salt that could not be written is regenerated on every invocation, so
    # every run derives a DIFFERENT machine_id for the same box and the ledger
    # sees a brand new machine each time. Report that plainly rather than
    # labelling it "install" and letting the instability look like real churn.
    return SaltInfo(salt, "install" if persisted else "ephemeral")


def load_or_create_salt(salt_path: Path | None = None) -> bytes:
    """Bytes-only accessor. PREFER ``load_salt``, which carries the scope.

    An id derived from bare bytes has ``salt_scope="unspecified"`` and is not
    safely comparable with a scoped one — same shape, different namespace. This
    exists for tests and for callers that genuinely only need key material.
    """
    if salt_path is not None:
        existing = _read_salt(salt_path)
        if existing is not None:
            return existing
        return _write_salt(salt_path, secrets.token_bytes(SALT_BYTES))[0]
    return load_salt().salt
