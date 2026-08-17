"""Per-install salt store (hermia-cfqv)."""
import stat

from hermia.identity.salt import load_or_create_salt


def test_creates_salt_and_is_stable_across_calls(tmp_path):
    p = tmp_path / "machine_salt"
    a = load_or_create_salt(p)
    b = load_or_create_salt(p)
    assert a == b
    assert len(a) == 32


def test_salt_file_is_owner_only(tmp_path):
    p = tmp_path / "machine_salt"
    load_or_create_salt(p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_distinct_paths_get_distinct_salts(tmp_path):
    assert load_or_create_salt(tmp_path / "a") != load_or_create_salt(tmp_path / "b")


def test_corrupt_salt_file_is_regenerated_not_crashed(tmp_path):
    p = tmp_path / "machine_salt"
    p.write_text("not-hex-at-all!!")
    s = load_or_create_salt(p)
    assert len(s) == 32


def test_wrong_length_salt_is_regenerated(tmp_path):
    """A truncated but valid-hex file must not yield a short salt."""
    p = tmp_path / "machine_salt"
    p.write_text("abcd")
    assert len(load_or_create_salt(p)) == 32


def test_unwritable_location_still_returns_a_usable_salt(tmp_path):
    """A read-only home must degrade to an ephemeral salt, not crash the CLI."""
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        s = load_or_create_salt(d / "machine_salt")
        assert len(s) == 32
    finally:
        d.chmod(0o700)


def test_existing_salt_with_loose_permissions_is_repaired_on_read(tmp_path):
    """A salt restored from backup or written by an older build must not stay
    world-readable just because its contents are valid."""
    p = tmp_path / "machine_salt"
    p.write_text("ab" * 32)
    p.chmod(0o644)
    load_or_create_salt(p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_salt_is_never_world_readable_even_under_a_loose_umask(tmp_path):
    """write_text() then chmod() would expose the secret in between."""
    import os

    old = os.umask(0o022)
    try:
        p = tmp_path / "machine_salt"
        load_or_create_salt(p)
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    finally:
        os.umask(old)
