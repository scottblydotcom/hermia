"""Fleet-scoped salt (hermia-cfqv)."""
import os
import stat

from hermia.identity.salt import load_or_create_salt, load_salt


def test_stable_across_calls_and_owner_only(tmp_path):
    p = tmp_path / "machine_salt"
    a = load_or_create_salt(p)
    assert a == load_or_create_salt(p)
    assert len(a) == 32
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_corrupt_or_short_salt_is_regenerated(tmp_path):
    p = tmp_path / "s"
    p.write_text("not-hex!!")
    assert len(load_or_create_salt(p)) == 32
    p.write_text("abcd")
    assert len(load_or_create_salt(p)) == 32


def test_existing_loose_permissions_are_repaired_on_read(tmp_path):
    p = tmp_path / "machine_salt"
    p.write_text("ab" * 32)
    p.chmod(0o644)
    load_or_create_salt(p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_never_world_readable_even_under_a_loose_umask(tmp_path):
    old = os.umask(0o022)
    try:
        p = tmp_path / "machine_salt"
        load_or_create_salt(p)
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    finally:
        os.umask(old)


def test_unwritable_location_still_returns_a_usable_salt(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        assert len(load_or_create_salt(d / "machine_salt")) == 32
    finally:
        d.chmod(0o700)


# --- FLEET SCOPE ---------------------------------------------------------
# Regression: a per-install salt meant the SAME fleet host derived a different
# id depending on which workstation ran the eval, so one machine appeared as
# two in the corpus.


def test_env_salt_wins_and_is_reported_as_fleet_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMIA_FLEET_SALT", "ab" * 32)
    info = load_salt(tmp_path / "fleet", tmp_path / "install")
    assert info.scope == "fleet:env"
    assert info.salt == bytes.fromhex("ab" * 32)


def test_env_passphrase_is_accepted_and_stretched(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMIA_FLEET_SALT", "a shared team phrase")
    info = load_salt(tmp_path / "fleet", tmp_path / "install")
    assert info.scope == "fleet:env"
    assert len(info.salt) == 32


def test_two_installs_sharing_a_fleet_salt_agree(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMIA_FLEET_SALT", "shared")
    a = load_salt(tmp_path / "f1", tmp_path / "i1")
    b = load_salt(tmp_path / "f2", tmp_path / "i2")
    assert a.salt == b.salt, "same fleet salt must give the same material"


def test_fleet_file_outranks_install_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMIA_FLEET_SALT", raising=False)
    fleet, install = tmp_path / "fleet", tmp_path / "install"
    fleet.write_text("cd" * 32)
    install.write_text("ef" * 32)
    info = load_salt(fleet, install)
    assert info.scope == "fleet:file"
    assert info.salt == bytes.fromhex("cd" * 32)


def test_falls_back_to_install_scope_and_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMIA_FLEET_SALT", raising=False)
    info = load_salt(tmp_path / "nofleet", tmp_path / "install")
    assert info.scope == "install"
    assert len(info.salt) == 32


def test_install_scope_is_not_silently_equivalent_to_fleet(tmp_path, monkeypatch):
    """Ids from different scopes are not comparable; the scope must be visible."""
    monkeypatch.delenv("HERMIA_FLEET_SALT", raising=False)
    a = load_salt(tmp_path / "nf1", tmp_path / "i1")
    b = load_salt(tmp_path / "nf2", tmp_path / "i2")
    assert a.scope == b.scope == "install"
    assert a.salt != b.salt
