"""Public API surface for machine identity (hermia-cfqv)."""


def test_public_api_exports():
    import hermia.identity as ident

    for name in (
        "HardwareFacts",
        "MachineIdentity",
        "HardwareProbe",
        "LocalProbe",
        "derive_machine_id",
        "load_or_create_salt",
        "check_identity_consistency",
    ):
        assert hasattr(ident, name), name


def test_end_to_end_local_identity_is_stable(tmp_path):
    from hermia.identity import LocalProbe, derive_machine_id, load_or_create_salt

    salt = load_or_create_salt(tmp_path / "salt")
    facts = LocalProbe().probe()
    a = derive_machine_id(facts, salt)
    b = derive_machine_id(facts, salt)
    assert a.machine_id == b.machine_id
    assert a.basis


def test_no_mac_anywhere_in_the_package_source():
    """Guard the core invariant against future well-meaning additions."""
    import pathlib

    import hermia.identity as ident

    pkg = pathlib.Path(ident.__file__).parent
    for py in pkg.glob("*.py"):
        text = py.read_text().lower()
        assert "getmac" not in text, py
        assert "uuid.getnode" not in text, py
        assert "mac_address" not in text, py
