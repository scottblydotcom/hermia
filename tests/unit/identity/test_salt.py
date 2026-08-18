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


# --- CodeRabbit: deterministic write-failure + creation race -------------


def test_write_failure_returns_an_ephemeral_salt_without_persisting(tmp_path, monkeypatch):
    """chmod 0500 does not stop a privileged process, so the directory-based
    test proves nothing when CI runs as root. Force the failure instead."""
    def boom(*a, **k):
        raise PermissionError("read-only")

    monkeypatch.setattr("hermia.identity.salt.os.open", boom)
    p = tmp_path / "machine_salt"
    assert len(load_or_create_salt(p)) == 32
    assert not p.exists()


def test_concurrent_first_creation_agrees_on_one_salt(tmp_path):
    """Two processes starting together must not each mint a salt and have the
    second clobber the first — ids either side of that would disagree."""
    from concurrent.futures import ThreadPoolExecutor

    p = tmp_path / "machine_salt"
    with ThreadPoolExecutor(max_workers=8) as pool:
        salts = list(pool.map(lambda _: load_or_create_salt(p), range(8)))
    assert len({s.hex() for s in salts}) == 1, "racing writers minted different salts"
    assert salts[0] == load_or_create_salt(p)


def test_passphrase_uses_a_slow_kdf_not_a_bare_digest(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setenv("HERMIA_FLEET_SALT", "a shared team phrase")
    info = load_salt(tmp_path / "f", tmp_path / "i")
    assert info.salt != hashlib.sha256(b"a shared team phrase").digest()
    assert info.salt == hashlib.scrypt(
        b"a shared team phrase", salt=b"hermia-fleet-salt-v1",
        n=2**14, r=8, p=1, dklen=32,
    )


def test_a_zero_byte_salt_file_is_repaired_not_re_minted_forever(tmp_path):
    """Left unrepaired, every run mints a throwaway salt and the machine gets a
    brand new id every single time, silently and forever."""
    p = tmp_path / "machine_salt"
    p.write_text("")
    first = load_or_create_salt(p)
    assert p.stat().st_size > 0, "corrupt salt file was never repaired"
    assert load_or_create_salt(p) == first


def test_a_truncated_salt_file_is_repaired(tmp_path):
    p = tmp_path / "machine_salt"
    p.write_text("abcd")
    first = load_or_create_salt(p)
    assert load_or_create_salt(p) == first
    assert len(first) == 32


def test_a_good_salt_is_never_clobbered_when_hard_links_are_unavailable(tmp_path, monkeypatch):
    """The no-hardlink fallback must not become an unconditional overwrite."""
    p = tmp_path / "machine_salt"
    original = load_or_create_salt(p)

    def no_links(*a, **k):
        raise OSError("hard links unsupported")

    monkeypatch.setattr("hermia.identity.salt.os.link", no_links)
    assert load_or_create_salt(p) == original


# --- gpt-oss: an unpersistable salt must announce itself -----------------


def test_unpersistable_salt_is_reported_as_ephemeral(tmp_path, monkeypatch):
    """A salt that cannot be written is regenerated every invocation, so every
    run derives a DIFFERENT id for the same box. Labelling that 'install' hides
    real instability behind a scope that implies stability."""
    monkeypatch.delenv("HERMIA_FLEET_SALT", raising=False)
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        info = load_salt(d / "fleet", d / "install")
        assert info.scope == "ephemeral"
        assert not info.is_stable
        assert len(info.salt) == 32
    finally:
        d.chmod(0o700)


def test_a_persisted_salt_reports_a_stable_scope(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMIA_FLEET_SALT", raising=False)
    info = load_salt(tmp_path / "fleet", tmp_path / "install")
    assert info.scope == "install"
    assert info.is_stable
    assert load_salt(tmp_path / "fleet", tmp_path / "install").salt == info.salt
