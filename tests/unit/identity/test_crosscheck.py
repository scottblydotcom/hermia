"""Label/machine cross-check ledger (hermia-cfqv)."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from hermia.identity.crosscheck import (
    check_identity_consistency,
    pending_conflicts,
    record_observation,
    resolve_conflict,
)


def test_first_observation_produces_no_warning(tmp_path):
    assert check_identity_consistency("host-a", "aaaa000000000000", tmp_path / "l.json") == []


def test_same_label_now_a_different_machine_warns(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-a", "aaaa000000000000", led)
    warns = check_identity_consistency("host-a", "bbbb111111111111", led)
    assert [w.kind for w in warns] == ["label_moved_machine"]
    assert "host-a" in warns[0].message


def test_same_machine_under_a_new_label_warns_as_rename(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-b", "cccc222222222222", led)
    assert [w.kind for w in check_identity_consistency("host-c", "cccc222222222222", led)] == [
        "machine_renamed"
    ]


def test_null_machine_id_never_warns_and_is_never_recorded(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-a", None, led)
    assert check_identity_consistency("host-a", None, led) == []
    assert check_identity_consistency("host-b", None, led) == []


def test_stable_pairing_stays_silent(tmp_path):
    led = tmp_path / "l.json"
    for _ in range(5):
        assert check_identity_consistency("host-d", "ffff555555555555", led) == []


@pytest.mark.parametrize(
    "payload",
    ["[]", '"str"', "123", "null", '{"foo": 1}',
     '{"label_to_id": "nope", "id_to_label": []}',
     '{"label_to_id": {"a": 5}, "id_to_label": {"b": null}}'],
)
def test_valid_json_of_the_wrong_shape_never_raises(tmp_path, payload):
    led = tmp_path / "l.json"
    led.write_text(payload)
    assert check_identity_consistency("host-a", "aaaa000000000000", led) == []
    record_observation("host-a", "aaaa000000000000", led)


def test_corrupt_ledger_degrades_silently(tmp_path):
    led = tmp_path / "l.json"
    led.write_text("{not json")
    assert check_identity_consistency("host-a", "eeee444444444444", led) == []


def test_unwritable_location_does_not_raise(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        record_observation("host-a", "1111000000000000", d / "l.json")
        assert check_identity_consistency("host-a", "1111000000000000", d / "l.json") == []
    finally:
        d.chmod(0o700)


# --- THE LOCK-IN BUG -----------------------------------------------------
# The old code recorded ONLY when no warning fired, so a misconfigured first run
# was blessed permanently: the CORRECT machine then alarmed forever while the
# WRONG one stayed silent, fixable only by hand-editing JSON.


def test_a_wrong_first_pairing_can_be_corrected(tmp_path):
    led = tmp_path / "l.json"
    # Run 1: YAML typo -- the label reaches the wrong box. Nothing to compare to.
    assert check_identity_consistency("lab-mac", "WRONG_BOX", led) == []
    # Run 2: typo fixed. The real machine answers and is flagged.
    assert [w.kind for w in check_identity_consistency("lab-mac", "REAL_MAC", led)] == [
        "label_moved_machine"
    ]
    # The alarm PERSISTS -- it is not absorbed on the next run.
    assert [w.kind for w in check_identity_consistency("lab-mac", "REAL_MAC", led)] == [
        "label_moved_machine"
    ]
    assert "lab-mac" in pending_conflicts(led)
    # ...but an operator can resolve it, without editing JSON by hand.
    resolve_conflict("lab-mac", "REAL_MAC", led)
    assert check_identity_consistency("lab-mac", "REAL_MAC", led) == []
    assert pending_conflicts(led) == {}


def test_the_wrong_box_now_alarms_after_resolution(tmp_path):
    """Having corrected the record, reverting to the wrong box must be caught."""
    led = tmp_path / "l.json"
    check_identity_consistency("lab-mac", "WRONG_BOX", led)
    resolve_conflict("lab-mac", "REAL_MAC", led)
    assert [w.kind for w in check_identity_consistency("lab-mac", "WRONG_BOX", led)] == [
        "label_moved_machine"
    ]


def test_conflict_records_both_sides(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-a", "AAA", led)
    check_identity_consistency("host-a", "BBB", led)
    conflict = pending_conflicts(led)["host-a"]
    assert conflict["expected"] == "AAA"
    assert conflict["observed"] == "BBB"


# --- CONCURRENCY ---------------------------------------------------------


def test_concurrent_observations_do_not_lose_hosts(tmp_path):
    led = tmp_path / "l.json"
    hosts = [(f"host-{i:02d}", f"{i:016x}") for i in range(24)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda h: record_observation(h[0], h[1], led), hosts))
    data = json.loads(led.read_text())
    assert len(data["label_to_id"]) == 24
    for label, mid in hosts:
        assert data["label_to_id"][label] == mid


def test_no_temp_files_left_behind(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-a", "1111000000000000", led)
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp"))
    assert leftovers == []


# --- CodeRabbit: ledger index consistency + conflict persistence ---------


def test_rebinding_a_label_removes_the_displaced_inverse_entry(tmp_path):
    """Writing only the new pair leaves the ledger claiming BOTH
    'host-a -> id-b' and 'id-a -> host-a' — mutually contradictory."""
    led = tmp_path / "l.json"
    record_observation("host-a", "id-a", led)
    resolve_conflict("host-a", "id-b", led)
    data = json.loads(led.read_text())
    assert data["label_to_id"] == {"host-a": "id-b"}
    assert "id-a" not in data["id_to_label"], "stale inverse entry survived"


def test_no_phantom_rename_warning_after_a_rebind(tmp_path):
    """A stale inverse entry makes a later sighting of the old machine fire
    machine_renamed against a binding that no longer exists."""
    led = tmp_path / "l.json"
    record_observation("host-a", "id-a", led)
    resolve_conflict("host-a", "id-b", led)
    assert check_identity_consistency("host-c", "id-a", led) == []


def test_rebinding_a_machine_removes_the_displaced_forward_entry(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-a", "id-a", led)
    record_observation("host-b", "id-a", led)
    data = json.loads(led.read_text())
    assert data["id_to_label"] == {"id-a": "host-b"}
    assert "host-a" not in data["label_to_id"]


def test_an_open_conflict_survives_the_original_pairing_returning(tmp_path):
    """A box swapped in for one run and swapped back would otherwise clear the
    conflict on the next run, leaving no trace that anything ever moved."""
    led = tmp_path / "l.json"
    record_observation("host-a", "id-a", led)
    assert [w.kind for w in check_identity_consistency("host-a", "id-b", led)] == [
        "label_moved_machine"
    ]
    warns = check_identity_consistency("host-a", "id-a", led)
    assert [w.kind for w in warns] == ["unresolved_conflict"]
    assert "host-a" in pending_conflicts(led)


def test_only_resolve_conflict_closes_an_open_conflict(tmp_path):
    led = tmp_path / "l.json"
    record_observation("host-a", "id-a", led)
    check_identity_consistency("host-a", "id-b", led)
    resolve_conflict("host-a", "id-a", led)
    assert pending_conflicts(led) == {}
    assert check_identity_consistency("host-a", "id-a", led) == []


def test_a_renamed_machine_does_not_poison_the_new_label_forever(tmp_path):
    """host-2 first sees M1 (which belongs to host-1) -> machine_renamed. The
    operator then points host-2 at its own hardware. It must be able to bind."""
    led = tmp_path / "l.json"
    record_observation("host-1", "M1", led)
    assert [w.kind for w in check_identity_consistency("host-2", "M1", led)] == [
        "machine_renamed"
    ]
    assert check_identity_consistency("host-2", "M2", led) == []
    assert pending_conflicts(led) == {}
    assert json.loads(led.read_text())["label_to_id"]["host-2"] == "M2"


def test_a_swapped_and_swapped_back_box_still_reports(tmp_path):
    """The other conflict shape must KEEP warning — this is the case where the
    label had a real prior binding."""
    led = tmp_path / "l.json"
    record_observation("host-a", "id-a", led)
    check_identity_consistency("host-a", "id-b", led)
    assert [w.kind for w in check_identity_consistency("host-a", "id-a", led)] == [
        "unresolved_conflict"
    ]


# --- gpt-oss: an advisory module must never block a run -------------------


def test_ledger_access_does_not_block_behind_a_held_lock(tmp_path):
    """A plain blocking flock parks the run behind whoever holds the lock; if
    that process is wedged the benchmark hangs with no output at all."""
    import fcntl
    import time

    led = tmp_path / "l.json"
    led.parent.mkdir(parents=True, exist_ok=True)
    holder = open(led.with_name(led.name + ".lock"), "w")
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        start = time.monotonic()
        record_observation("host-a", "id-a", led)          # must not hang
        assert check_identity_consistency("host-a", "id-a", led) == []
        assert time.monotonic() - start < 10, "ledger access blocked on a held lock"
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()


def test_a_corrupt_ledger_is_preserved_not_silently_discarded(tmp_path):
    """Every recorded pairing is about to be dropped; leave the evidence."""
    led = tmp_path / "l.json"
    led.write_text('{"label_to_id": {"host-a": "id-a"}  <<<broken')
    assert check_identity_consistency("host-b", "id-b", led) == []
    corrupt = led.with_name(led.name + ".corrupt")
    assert corrupt.exists()
    assert "host-a" in corrupt.read_text()
