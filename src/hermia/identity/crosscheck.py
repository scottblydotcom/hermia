"""Label/machine cross-check ledger (hermia-cfqv).

This is the high-value part. A local ledger remembers which ``machine_id`` was
last seen under which operator label, and warns when the two stop agreeing.

That check alone would have caught hermia-fqod **at dispatch time** rather than
a month later during analysis: a fleet YAML named one machine while a
different one answered, and nothing anywhere noticed. It also covers the case where one machine
accumulated three different names over three months.

Advisory only. Every function here degrades to silence rather than raising, and
nothing in this module may block or fail a run.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LEDGER_PATH = Path.home() / ".hermia" / "machine_ledger.json"

_Ledger = dict[str, dict[str, str]]

# fleet.py runs hosts in a ThreadPoolExecutor, so per-host checks land here
# concurrently. Without this the read-modify-write below interleaves and one
# worker's pairing is lost, leaving that host silently unprotected against the
# very swap this module detects. In-process only: a second hermia process
# writing the same ledger is still last-writer-wins (atomic, but not merged).
_LEDGER_LOCK = threading.Lock()


@dataclass(frozen=True)
class IdentityWarning:
    """kind is ``label_moved_machine`` or ``machine_renamed``."""

    kind: str
    message: str


def _empty() -> _Ledger:
    return {"label_to_id": {}, "id_to_label": {}}


def _load_ledger(ledger_path: Path) -> _Ledger:
    """Load the ledger, returning an empty one on ANY problem.

    Shape is validated, not assumed: a file containing valid JSON of the wrong
    shape (``[]``, ``{"foo": 1}``, a nested non-string value) must degrade to
    empty rather than raising a KeyError/TypeError deep inside a caller. Testing
    only malformed JSON would miss that entirely.
    """
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - advisory only, never raise
        return _empty()

    if not isinstance(data, dict):
        return _empty()

    out = _empty()
    for section in ("label_to_id", "id_to_label"):
        raw = data.get(section)
        if isinstance(raw, dict):
            out[section] = {
                k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)
            }
    return out


def _save_ledger(ledger_path: Path, data: _Ledger) -> None:
    """Write the ledger atomically: temp file in the same dir, then os.replace.

    A partial write would leave truncated JSON, which _load_ledger treats as
    empty — silently discarding every previously recorded pairing and disarming
    the swap detection this module exists for.
    """
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = ledger_path.with_name(f"{ledger_path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, ledger_path)
    except OSError:
        pass  # read-only home: skip persistence, never crash the run


def record_observation(
    label: str, machine_id: str | None, ledger_path: Path | None = None
) -> None:
    """Persist a (label, machine_id) pairing in both directions.

    A ``machine_id`` of ``None`` means NOT MEASURED and is never recorded —
    storing it would make "we don't know" look like a machine, and every
    unidentified host would then collide into one identity.
    """
    if machine_id is None:
        return
    path = DEFAULT_LEDGER_PATH if ledger_path is None else ledger_path
    with _LEDGER_LOCK:
        ledger = _load_ledger(path)
        ledger["label_to_id"][label] = machine_id
        ledger["id_to_label"][machine_id] = label
        _save_ledger(path, ledger)


def check_identity_consistency(
    label: str, machine_id: str | None, ledger_path: Path | None = None
) -> list[IdentityWarning]:
    """Return warnings when a label and a machine stop agreeing.

    Side effect, deliberate and worth knowing about: when the pairing is
    consistent (or new), it is RECORDED. That makes the check self-bootstrapping
    at dispatch time — the first run of a host teaches the ledger, and a later
    swap is caught. When a warning fires nothing is recorded, so the alarm
    persists across runs until an operator resolves it rather than being
    silently absorbed on the second run.
    """
    if machine_id is None:
        return []

    path = DEFAULT_LEDGER_PATH if ledger_path is None else ledger_path
    ledger = _load_ledger(path)
    warnings: list[IdentityWarning] = []

    previous_id = ledger["label_to_id"].get(label)
    if previous_id is not None and previous_id != machine_id:
        warnings.append(
            IdentityWarning(
                kind="label_moved_machine",
                message=(
                    f"Host label '{label}' previously identified machine "
                    f"'{previous_id}' but now identifies '{machine_id}'. The name "
                    f"may have been moved to different hardware."
                ),
            )
        )

    previous_label = ledger["id_to_label"].get(machine_id)
    if previous_label is not None and previous_label != label:
        warnings.append(
            IdentityWarning(
                kind="machine_renamed",
                message=(
                    f"Machine '{machine_id}' was previously labelled "
                    f"'{previous_label}' and is now labelled '{label}'. Rows from "
                    f"both labels belong to one machine."
                ),
            )
        )

    if not warnings:
        record_observation(label, machine_id, path)
    return warnings
