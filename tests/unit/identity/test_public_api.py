"""Public API surface (hermia-cfqv)."""
import pathlib


def test_public_api_exports():
    import hermia.identity as ident

    for name in (
        "MachineIdentifiers", "MachineCapabilities", "MachineIdentity",
        "MachineObservation", "HardwareProbe", "LocalProbe", "SaltInfo",
        "derive_machine_id", "load_salt", "check_identity_consistency",
        "resolve_conflict", "pending_conflicts",
    ):
        assert hasattr(ident, name), name


def test_end_to_end_local_identity_is_stable(tmp_path):
    from hermia.identity import LocalProbe, derive_machine_id, load_or_create_salt

    salt = load_or_create_salt(tmp_path / "salt")
    obs = LocalProbe().probe()
    a = derive_machine_id(obs.identifiers, salt)
    b = derive_machine_id(obs.identifiers, salt)
    assert a.machine_id == b.machine_id
    assert a.source and a.basis


def test_identity_never_consumes_a_capability_or_network_identifier():
    """Guards the core invariant against future well-meaning additions.

    Substring matching would be wrong here -- "match" contains "mac". Match on
    whole identifiers only.
    """
    import re

    import hermia.identity as ident

    derive = (pathlib.Path(ident.__file__).parent / "derive.py").read_text()
    banned = (
        "ram_bytes", "cpu_brand", "logical_cores", "model_identifier",
        "nic_mac", "mac_address", "getnode", "hostname", "ip_address",
        "MachineCapabilities",
    )
    for token in banned:
        assert not re.search(rf"\b{re.escape(token)}\b", derive), (
            f"{token} must never reach identity derivation"
        )
