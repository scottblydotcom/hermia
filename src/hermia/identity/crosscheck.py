"""Label/machine cross-check ledger (hermia-cfqv).

A local ledger remembers which ``machine_id`` was last seen under which operator
label, and warns when the two stop agreeing. That check is what catches a fleet
YAML naming one machine while a different one answers — at dispatch time, rather
than a month later during analysis.

Two defects from the first version are fixed here.

1. IT LOCKED IN THE FIRST THING IT SAW. The old code recorded an observation only
   when no warning fired. So if the very first run was misconfigured, the WRONG
   pairing was blessed permanently: afterwards the correct machine raised an
   alarm on every run while the wrong one stayed silent, and the only escape was
   hand-editing JSON. Verified in practice, not theorised. Conflicts are now
   recorded explicitly and cleared through ``resolve_conflict``, so the alarm
   persists until a human decides — but a human CAN decide.

2. IT RACED ACROSS PROCESSES. A thread lock is not enough when two hermia runs
   share a home directory. Writes now take an advisory file lock and land
   atomically.

Advisory only. Nothing here raises, and nothing here blocks a run.
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # POSIX only; elsewhere the thread lock plus atomic replace still apply.
    import fcntl
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None  # type: ignore[assignment]

DEFAULT_LEDGER_PATH = Path.home() / ".hermia" / "machine_ledger.json"

_Ledger = dict[str, Any]
# Reentrant: a caller reaching this module again from inside a logging handler
# or error path would otherwise self-deadlock rather than merely misbehave.
_LEDGER_LOCK = threading.RLock()


@dataclass(frozen=True)
class IdentityWarning:
    """kind is ``label_moved_machine`` or ``machine_renamed``."""

    kind: str
    message: str


def _empty() -> _Ledger:
    return {"label_to_id": {}, "id_to_label": {}, "conflicts": {}}


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Serialise ledger access across threads AND processes."""
    with _LEDGER_LOCK:
        handle = None
        if fcntl is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = open(path.with_name(path.name + ".lock"), "w")  # noqa: SIM115
                fcntl.flock(handle, fcntl.LOCK_EX)
            except OSError:
                handle = None
        try:
            yield
        finally:
            if handle is not None:
                try:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                finally:
                    handle.close()


def _load(path: Path) -> _Ledger:
    """Load the ledger, returning an empty one on ANY problem.

    Shape is validated rather than assumed: valid JSON of the wrong shape (``[]``,
    ``{"foo": 1}``) must degrade to empty instead of raising a KeyError inside a
    caller. Testing only malformed JSON would miss that entirely.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
    raw_conflicts = data.get("conflicts")
    if isinstance(raw_conflicts, dict):
        out["conflicts"] = {
            k: v for k, v in raw_conflicts.items() if isinstance(k, str)
        }
    return out


def _save(path: Path, data: _Ledger) -> None:
    """Atomic write: temp file in the same dir, then os.replace.

    A partial write would leave truncated JSON, which ``_load`` treats as empty —
    silently discarding every recorded pairing and disarming the whole check.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # read-only home: skip persistence, never crash the run


def _still_disputed(conflict: dict[str, Any], machine_id: str) -> bool:
    """Is a recorded conflict still live for the machine now being observed?

    Two different situations get recorded as a conflict, and only one of them
    should keep blocking:

    * The label HAD a binding and something else answered to it. The dispute is
      about this label, so it stays open even once the original machine returns
      — otherwise a box swapped in for one run and swapped back out clears
      itself and leaves no trace that anything moved.
    * The label had NO binding and the conflict came from the machine already
      answering to another name. Once this label settles on a different,
      unclaimed machine that dispute is moot FOR THIS LABEL. Keeping it open
      would permanently block a freshly renamed host from ever binding, while
      warning forever about a machine no longer involved.
    """
    if conflict.get("expected") is not None:
        return True
    return conflict.get("observed") == machine_id


def _bind(ledger: _Ledger, label: str, machine_id: str) -> None:
    """Bind label<->machine, REMOVING whatever each side displaced.

    The two indexes must stay mutually consistent. Writing only the new pair
    leaves the old inverse entry behind, so the ledger simultaneously claims
    `label -> new_id` and `old_id -> label`. A later sighting of old_id under a
    different name then fires `machine_renamed` citing a binding that no longer
    exists — a warning about nothing, which is how operators learn to ignore
    warnings.
    """
    displaced_id = ledger["label_to_id"].get(label)
    if (
        displaced_id is not None
        and displaced_id != machine_id
        and ledger["id_to_label"].get(displaced_id) == label
    ):
        del ledger["id_to_label"][displaced_id]

    displaced_label = ledger["id_to_label"].get(machine_id)
    if (
        displaced_label is not None
        and displaced_label != label
        and ledger["label_to_id"].get(displaced_label) == machine_id
    ):
        del ledger["label_to_id"][displaced_label]

    ledger["label_to_id"][label] = machine_id
    ledger["id_to_label"][machine_id] = label
    ledger["conflicts"].pop(label, None)


def record_observation(
    label: str, machine_id: str | None, ledger_path: Path | None = None
) -> None:
    """Persist a (label, machine_id) pairing in both directions.

    ``machine_id`` of ``None`` means NOT MEASURED and is never recorded: storing
    it would make "we don't know" look like a machine, and every unidentified
    host would collide into one identity.
    """
    if machine_id is None:
        return
    path = DEFAULT_LEDGER_PATH if ledger_path is None else ledger_path
    with _locked(path):
        ledger = _load(path)
        _bind(ledger, label, machine_id)
        _save(path, ledger)


def resolve_conflict(
    label: str, machine_id: str, ledger_path: Path | None = None
) -> None:
    """Operator decision: ``label`` legitimately identifies ``machine_id`` now.

    This is the escape hatch whose absence made the old ledger unfixable without
    editing JSON by hand. It rebinds the label, clears the conflict, and lets
    subsequent runs go quiet.
    """
    record_observation(label, machine_id, ledger_path)


def pending_conflicts(ledger_path: Path | None = None) -> dict[str, Any]:
    """Conflicts awaiting an operator decision, keyed by label."""
    path = DEFAULT_LEDGER_PATH if ledger_path is None else ledger_path
    conflicts = _load(path)["conflicts"]
    return dict(conflicts)


def check_identity_consistency(
    label: str, machine_id: str | None, ledger_path: Path | None = None
) -> list[IdentityWarning]:
    """Return warnings when a label and a machine stop agreeing.

    A NEW, consistent pairing is recorded automatically, so the check is
    self-bootstrapping. A CONFLICTING pairing is recorded as a conflict and keeps
    warning on every run until ``resolve_conflict`` is called — never silently
    absorbed on the second run, and never permanently stuck either.

    An OPEN conflict keeps warning even once the original pairing reappears. A
    box swapped in for one run and swapped back out would otherwise clear itself
    on the next run, leaving no trace that anything moved — which is precisely
    the silent absorption this exists to prevent. Only ``resolve_conflict``
    closes it.
    """
    if machine_id is None:
        return []

    path = DEFAULT_LEDGER_PATH if ledger_path is None else ledger_path
    with _locked(path):
        ledger = _load(path)
        warnings: list[IdentityWarning] = []

        previous_id = ledger["label_to_id"].get(label)
        if previous_id is not None and previous_id != machine_id:
            warnings.append(
                IdentityWarning(
                    kind="label_moved_machine",
                    message=(
                        f"Host label '{label}' previously identified machine "
                        f"'{previous_id}' but now identifies '{machine_id}'. If "
                        f"intended, resolve it explicitly; otherwise the label "
                        f"may be pointed at the wrong hardware."
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
                        f"'{previous_label}' and is now labelled '{label}'. Rows "
                        f"under both labels belong to one machine."
                    ),
                )
            )

        open_conflict = ledger["conflicts"].get(label)
        if warnings:
            ledger["conflicts"][label] = {
                "observed": machine_id,
                "expected": previous_id,
            }
        elif isinstance(open_conflict, dict) and _still_disputed(
            open_conflict, machine_id
        ):
            # Pairing looks fine again, but nobody adjudicated the earlier
            # disagreement. Keep reporting it; do NOT rebind.
            warnings.append(
                IdentityWarning(
                    kind="unresolved_conflict",
                    message=(
                        f"Host label '{label}' currently identifies "
                        f"'{machine_id}', but an earlier disagreement on this "
                        f"label (observed '{open_conflict.get('observed')}') "
                        f"was never resolved. Resolve it explicitly to clear "
                        f"this warning."
                    ),
                )
            )
        else:
            _bind(ledger, label, machine_id)
        _save(path, ledger)
    return warnings
