"""Tests for identity stamping on result rows (hermia-cfqv wiring).

build_identity_stamp is the unit under test; the fqod-guard test drives it
through run_test to prove a REMOTE row never carries the orchestrator's local
identity.
"""
from hermia.identity.cache import IdentityCache
from hermia.identity.salt import SaltInfo
from hermia.identity.transport_config import IdentityTransport
from hermia.identity.types import (
    MachineCapabilities,
    MachineIdentifiers,
    MachineObservation,
)
from hermia.runner import build_identity_stamp

SALT = SaltInfo(b"\x11" * 32, "fleet:test")


def _obs(serial, vram=None):
    return MachineObservation(
        MachineIdentifiers(hardware_serial=serial),
        MachineCapabilities(vram_bytes=vram),
    )


def test_ssh_transport_stamps_remote_fingerprint():
    stamp = build_identity_stamp(
        transport=IdentityTransport("ssh", "rampagev"),
        salt=SALT,
        cache=IdentityCache(),
        endpoint_size_vram_gb=20.0,
        probe_factory=lambda t: _obs("SN-REMOTE-1", vram=32 * 1024**3),
    )
    assert stamp["machine_fingerprint"] is not None
    assert stamp["machine_id_source"] == "hardware-serial"
    assert stamp["identity_crosscheck"] == "ok"
    assert "machine_id" not in stamp  # never emits the human-alias key
    # The fingerprint MUST be the salted hash, never the raw identifier — the core
    # hermia-cfqv invariant. A raw firmware UUID/serial on a row is the leak the salt
    # exists to prevent. (Rubric gap closed 2026-08-19: an implementation that returned
    # the raw serial passed the weaker assertions above.)
    from hermia.identity.derive import derive_machine_id
    expected_hash = derive_machine_id(
        MachineIdentifiers(hardware_serial="SN-REMOTE-1"), SALT
    ).machine_id
    assert stamp["machine_fingerprint"] == expected_hash
    assert stamp["machine_fingerprint"] != "SN-REMOTE-1"


def test_api_transport_stamps_explicit_null():
    stamp = build_identity_stamp(
        transport=IdentityTransport("api", None),
        salt=SALT,
        cache=IdentityCache(),
        endpoint_size_vram_gb=None,
        probe_factory=lambda t: _obs("SHOULD-NOT-BE-CALLED"),
    )
    assert stamp["machine_fingerprint"] is None
    assert stamp["machine_id_source"] == "none"
    assert stamp["identity_crosscheck"] == "unchecked"


def test_crosscheck_flags_mismatched_mapping():
    stamp = build_identity_stamp(
        transport=IdentityTransport("ssh", "small-box"),
        salt=SALT,
        cache=IdentityCache(),
        endpoint_size_vram_gb=70.0,
        probe_factory=lambda t: _obs("SN-24GB", vram=24 * 1024**3),
    )
    assert stamp["identity_crosscheck"] == "mismatch"
