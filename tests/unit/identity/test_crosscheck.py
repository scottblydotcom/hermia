"""Label/machine cross-check ledger (hermia-cfqv).

This is the check that would have caught hermia-fqod at dispatch time instead
of a month later during analysis.
"""
import json

import pytest

from hermia.identity.crosscheck import check_identity_consistency, record_observation


def test_first_observation_produces_no_warning(tmp_path):
    led = tmp_path / "ledger.json"
    assert check_identity_consistency("host-a", "aaaa000000000000", led) == []


def test_same_label_now_a_different_machine_warns(tmp_path):
    """A name that silently starts pointing at different hardware."""
    led = tmp_path / "ledger.json"
    record_observation("host-a", "aaaa000000000000", led)
    warns = check_identity_consistency("host-a", "bbbb111111111111", led)
    assert len(warns) == 1
    assert warns[0].kind == "label_moved_machine"
    assert "host-a" in warns[0].message


def test_same_machine_under_a_new_label_warns_as_rename(tmp_path):
    """One box under several names."""
    led = tmp_path / "ledger.json"
    record_observation("host-b", "cccc222222222222", led)
    warns = check_identity_consistency("host-c", "cccc222222222222", led)
    assert len(warns) == 1
    assert warns[0].kind == "machine_renamed"


def test_unknown_machine_id_never_warns(tmp_path):
    """A null id means 'not measured'. It must not be treated as a machine."""
    led = tmp_path / "ledger.json"
    record_observation("host-a", "dddd333333333333", led)
    assert check_identity_consistency("host-a", None, led) == []


def test_corrupt_ledger_degrades_to_no_warnings_and_does_not_raise(tmp_path):
    led = tmp_path / "ledger.json"
    led.write_text("{not json")
    assert check_identity_consistency("host-a", "eeee444444444444", led) == []


def test_missing_ledger_does_not_raise(tmp_path):
    assert check_identity_consistency("host-a", "eeee444444444444", tmp_path / "nope.json") == []


def test_stable_pairing_repeated_many_times_stays_silent(tmp_path):
    led = tmp_path / "ledger.json"
    for _ in range(5):
        record_observation("host-d", "ffff555555555555", led)
        assert check_identity_consistency("host-d", "ffff555555555555", led) == []


def test_record_observation_never_persists_a_null_id(tmp_path):
    """Recording a null would make 'not measured' look like a machine."""
    led = tmp_path / "ledger.json"
    record_observation("host-a", None, led)
    assert check_identity_consistency("host-b", None, led) == []


def test_both_warnings_can_fire_together(tmp_path):
    """Label points somewhere new AND the machine had another name."""
    led = tmp_path / "ledger.json"
    record_observation("label-a", "1111000000000000", led)
    record_observation("label-b", "2222000000000000", led)
    warns = check_identity_consistency("label-a", "2222000000000000", led)
    kinds = {w.kind for w in warns}
    assert kinds == {"label_moved_machine", "machine_renamed"}


# ---------------------------------------------------------------------------
# Ledger robustness. The first implementation json.loads()'d the file and then
# indexed ledger["label_to_id"] directly, so a file containing VALID json of the
# wrong shape raised KeyError/TypeError out of a function documented never to
# raise. Testing only malformed json ("{not json") missed this completely.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        '"just a string"',
        "123",
        "null",
        '{"foo": 1}',
        '{"label_to_id": "not-a-dict", "id_to_label": []}',
        '{"label_to_id": {"a": 5}, "id_to_label": {"b": null}}',
    ],
)
def test_valid_json_of_the_wrong_shape_never_raises(tmp_path, payload):
    led = tmp_path / "ledger.json"
    led.write_text(payload)
    assert check_identity_consistency("host-a", "aaaa000000000000", led) == []
    record_observation("host-a", "aaaa000000000000", led)


def test_wrong_shape_ledger_is_repaired_on_next_write(tmp_path):
    led = tmp_path / "ledger.json"
    led.write_text('{"label_to_id": "not-a-dict"}')
    record_observation("host-a", "aaaa000000000000", led)
    data = json.loads(led.read_text())
    assert data["label_to_id"]["host-a"] == "aaaa000000000000"
    assert data["id_to_label"]["aaaa000000000000"] == "host-a"


def test_consistent_check_records_so_a_later_swap_is_caught(tmp_path):
    """Documented side effect: check() bootstraps the ledger when consistent."""
    led = tmp_path / "ledger.json"
    assert check_identity_consistency("host-a", "1111000000000000", led) == []
    warns = check_identity_consistency("host-a", "2222000000000000", led)
    assert [w.kind for w in warns] == ["label_moved_machine"]


def test_a_firing_warning_persists_across_runs(tmp_path):
    """A warning must not be silently absorbed on the second run."""
    led = tmp_path / "ledger.json"
    record_observation("host-a", "1111000000000000", led)
    for _ in range(3):
        warns = check_identity_consistency("host-a", "2222000000000000", led)
        assert [w.kind for w in warns] == ["label_moved_machine"]


def test_unwritable_ledger_location_does_not_raise(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        record_observation("host-a", "1111000000000000", d / "ledger.json")
        assert check_identity_consistency("host-a", "1111000000000000", d / "l.json") == []
    finally:
        d.chmod(0o700)


def test_concurrent_observations_do_not_lose_hosts(tmp_path):
    """fleet.py runs hosts in a ThreadPoolExecutor; an unlocked
    read-modify-write drops pairings and silently disarms swap detection."""
    from concurrent.futures import ThreadPoolExecutor

    led = tmp_path / "ledger.json"
    hosts = [(f"host-{i:02d}", f"{i:016x}") for i in range(24)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda h: record_observation(h[0], h[1], led), hosts))

    data = json.loads(led.read_text())
    assert len(data["label_to_id"]) == 24, "a concurrent write clobbered a host"
    for label, mid in hosts:
        assert data["label_to_id"][label] == mid


def test_no_temp_files_are_left_behind(tmp_path):
    led = tmp_path / "ledger.json"
    record_observation("host-a", "1111000000000000", led)
    assert [p.name for p in tmp_path.iterdir()] == ["ledger.json"]
