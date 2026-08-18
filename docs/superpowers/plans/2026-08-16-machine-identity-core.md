# Machine Identity Core (hermia-cfqv) Implementation Plan

> **STATUS 2026-08-16 — PARTLY SUPERSEDED. Read this box before the plan.**
>
> Two independent outside-family adversarial reviews (Antigravity, and gpt-oss:120b
> run locally) rejected the identity model this plan implements, and a proposed
> weighted-threshold successor, for the same reason:
>
> > Any threshold loose enough to tolerate a hardware repair merges two identical
> > laptops; any threshold tight enough to keep them apart is just an exact match
> > on the strongest identifier.
>
> What shipped instead is an **identifier / capability split**:
> * IDENTITY comes only from non-transferable identifiers (firmware UUID, hardware
>   serial, minted on-host token), matched EXACTLY in a fixed preference order.
> * CAPABILITIES (CPU, memory, GPU, MAC) are recorded and never hashed, so a RAM
>   upgrade is a visible fact rather than a new machine.
> * The salt is FLEET-scoped, not per-install — a per-install salt made the same
>   host derive different ids from different workstations.
>
> Tasks 1-7 below remain accurate for structure, file layout, and the
> never-guess rule. The `HardwareFacts` type and the "platform_uuid REQUIRED,
> else null" rule are superseded by `MachineIdentifiers` / `MachineCapabilities`
> and the preference order in `derive.py`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive a salted, locally-unique `machine_id` from identifiers bound to the *machine* (not to a detachable network adapter), so a row's identity stops depending on an operator-typed name or a DHCP reservation.

**Architecture:** A new `src/hermia/identity/` package with four focused modules: a probe layer that measures hardware facts (local probe now, remote probes later behind a Protocol), a derivation layer that HMACs those facts under a per-install salt, a salt store, and a cross-check ledger that warns when a label and a machine stop agreeing. Nothing is wired into result rows in this PR — see Non-Goals.

**Tech Stack:** Python 3.11+, stdlib only (`hmac`, `hashlib`, `secrets`, `json`, `subprocess`, `tomllib`, `platform`), pytest.

---

## Why this exists (read before changing the design)

`hermia-fqod`: 870 rows were attributed to an Apple M1 Mac but ran on an AMD Vega/Vulkan Linux box. Nothing in the schema could catch it, because a row's machine identity is `fleet_host_name` — an operator-typed string in a fleet YAML, verified against nothing. Host identity has now lied in **four** independent ways in this corpus:

1. One machine under several names (`host-f` ×3, `host-b` ×3).
2. SSH tunnel ports repointed between machines over time.
3. DHCP reservations bound to **detachable USB/Thunderbolt dongles** — move the dongle, and the IP follows the accessory, not the computer.
4. A Thunderbolt **dock** MAC, which identifies the dock; whichever laptop is docked inherits the address.

## Non-negotiable design constraints

- **EXCLUDE MAC entirely.** A MAC-derived id migrates with a dongle or dock. Excluding it means a dongle swap produces *no* identity change — correct. (Including it would produce a spurious "new machine", which is a lesser failure than two machines sharing an identity, but still wrong.)
- **`platform_uuid` is REQUIRED.** CPU brand + RAM bytes alone are *not* an identity: a fleet commonly contains **several laptops of the same model and memory size**. Identical models would collide. If the platform UUID cannot be measured, `machine_id` is `None` — never a partial hash.
- **Never guess.** Every failure path yields `machine_id=None` plus a machine-readable `basis`. There is no default, no fallback identity, no "unknown-1".
- **Salt and raw hardware ids never leave the machine.** Not in a row, not in an export, not in a log line.

## Non-Goals for this PR (deliberate — do not "helpfully" add)

- **Do NOT wire `machine_id` into result rows / `runner.py`.** For a fleet run, hermia runs on Scott's laptop while the model runs on a remote host. Stamping the *local* machine onto a *remote* row would manufacture exactly the misleading field this work exists to eliminate. Row wiring lands with the remote-transport decision (deferred by Scott 2026-08-16).
- **Do NOT add remote probes.** Define the Protocol; implement `LocalProbe` only.
- **Do NOT modify `src/hermia/submit.py`.** See the salt-storage note below.

## Naming collision — resolve before wiring (not in this PR)

Corpus rows already carry `machine_id` / `machine_id_basis`, added 2026-08-15 as an *additive alias* for the historical corpus (values are human names like `host-b`; table at `results/machine_aliases.json`). This PR's runtime `machine_id` is a **16-hex salted hash** — same name, different semantics. They must not meet in one row. This PR ships no row field, so nothing collides yet; the wiring PR must rename one of them. File a bead when wiring.

## Salt storage — why a separate file

`submit.py:load_or_create_install_id` writes config with
`config_path.write_text('[hermia]\ninstall_id = "..."\n')` — a **whole-file overwrite**. A salt stored in `~/.hermia/config.toml` would be silently destroyed the first time an install_id is regenerated (absent or malformed file). Rather than inherit that hazard or edit an out-of-scope module, the salt lives in its own file: `~/.hermia/machine_salt`, mode `0600`. Log the clobbering writer as a separate bead.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/hermia/identity/__init__.py` | Public API re-exports only: `HardwareFacts`, `MachineIdentity`, `HardwareProbe`, `LocalProbe`, `derive_machine_id`, `load_or_create_salt`, `check_identity_consistency`. |
| `src/hermia/identity/types.py` | Frozen dataclasses + the `HardwareProbe` Protocol. No I/O. |
| `src/hermia/identity/probes.py` | `LocalProbe`: per-OS measurement of platform UUID / CPU brand / RAM bytes. All subprocess use. |
| `src/hermia/identity/derive.py` | Facts + salt → `MachineIdentity`. Pure; no I/O. |
| `src/hermia/identity/salt.py` | Load-or-create the per-install salt at `~/.hermia/machine_salt`. |
| `src/hermia/identity/crosscheck.py` | Label↔id ledger at `~/.hermia/machine_ledger.json`; returns warnings, never raises. |
| `src/hermia/sink/anonymize.py` *(modify)* | Add `assign_machine_pseudonyms()`. Do **not** add `machine_id` to `SUBMIT_WHITELIST`. |
| `tests/unit/identity/test_types.py` … `test_crosscheck.py` | One test module per source module. |

---

## Task 1: Types and Protocol

**Files:**
- Create: `src/hermia/identity/types.py`
- Test: `tests/unit/identity/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from hermia.identity.types import HardwareFacts, MachineIdentity


def test_hardware_facts_is_frozen():
    f = HardwareFacts(platform_uuid="U", cpu_brand="C", ram_bytes=1, os_family="darwin")
    with pytest.raises(Exception):
        f.platform_uuid = "other"  # type: ignore[misc]


def test_hardware_facts_defaults_unmeasured_to_none_not_empty_string():
    f = HardwareFacts(platform_uuid=None, cpu_brand=None, ram_bytes=None, os_family="linux")
    assert f.platform_uuid is None
    assert f.cpu_brand is None
    assert f.ram_bytes is None
    assert f.unavailable == ()


def test_is_identifiable_requires_platform_uuid():
    """CPU+RAM alone must NOT count: identical laptop models share both."""
    assert HardwareFacts("U", "Apple M1 Pro", 17179869184, "darwin").is_identifiable
    assert not HardwareFacts(None, "Apple M1 Pro", 17179869184, "darwin").is_identifiable


def test_machine_identity_null_id_still_carries_a_basis():
    m = MachineIdentity(machine_id=None, basis="unavailable:no-platform-uuid", os_family="linux")
    assert m.machine_id is None
    assert m.basis
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/identity/test_types.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hermia.identity'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Types for machine identity. No I/O, no subprocess — pure data."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class HardwareFacts:
    """Facts measured ON a machine. ``None`` means NOT MEASURED — never guessed."""

    platform_uuid: str | None
    cpu_brand: str | None
    ram_bytes: int | None
    os_family: str
    unavailable: tuple[str, ...] = field(default=())

    @property
    def is_identifiable(self) -> bool:
        """True only when the strong, machine-bound identifier was measured.

        CPU brand and RAM size are entropy, NOT identity: two identical laptops
        share both. Requiring platform_uuid is what stops two laptops of
        identical model and memory from hashing to the same machine_id.
        """
        return bool(self.platform_uuid)


@dataclass(frozen=True)
class MachineIdentity:
    """A derived identity. ``machine_id is None`` is a valid, explicit outcome."""

    machine_id: str | None
    basis: str
    os_family: str


class HardwareProbe(Protocol):
    """Measures hardware facts for one machine.

    ``LocalProbe`` implements this for the machine hermia runs on. Remote
    probes (SSH, agent) implement the same Protocol later; nothing else in the
    package may assume the facts came from localhost.
    """

    def probe(self) -> HardwareFacts: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/identity/test_types.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hermia/identity/types.py tests/unit/identity/test_types.py
git commit -m "feat(identity): hardware fact and identity types (hermia-cfqv)"
```

---

## Task 2: Salt store

**Files:**
- Create: `src/hermia/identity/salt.py`
- Test: `tests/unit/identity/test_salt.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/identity/test_salt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hermia.identity.salt'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Per-install salt for machine_id derivation.

Stored in its OWN file, not in ``~/.hermia/config.toml``: that file is written
with a whole-file overwrite by ``submit.load_or_create_install_id``, which would
silently destroy a salt stored beside install_id.

The salt is what makes machine_id locally unique but globally meaningless. An
UNSALTED hash of platform-uuid+cpu+ram is trivially confirmable — the candidate
space is small enough that anyone holding a machine can hash it and confirm a
match, re-identifying the box and leaking fleet composition.
"""
from __future__ import annotations

import secrets
from pathlib import Path

SALT_BYTES = 32
DEFAULT_SALT_PATH = Path.home() / ".hermia" / "machine_salt"


def load_or_create_salt(salt_path: Path | None = None) -> bytes:
    """Return the per-install salt, creating and persisting it if absent.

    A missing, unreadable, or malformed file is regenerated. An unwritable
    location yields an ephemeral salt for this process rather than raising —
    the CLI keeps working, but machine_id will not be stable across runs.
    """
    path = DEFAULT_SALT_PATH if salt_path is None else salt_path
    try:
        raw = bytes.fromhex(path.read_text(encoding="utf-8").strip())
        if len(raw) == SALT_BYTES:
            return raw
    except (OSError, ValueError):
        pass

    salt = secrets.token_bytes(SALT_BYTES)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(salt.hex(), encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        pass  # ephemeral for this process
    return salt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/identity/test_salt.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hermia/identity/salt.py tests/unit/identity/test_salt.py
git commit -m "feat(identity): per-install salt store in its own file (hermia-cfqv)"
```

---

## Task 3: Derivation

**Files:**
- Create: `src/hermia/identity/derive.py`
- Test: `tests/unit/identity/test_derive.py`

- [ ] **Step 1: Write the failing test**

```python
from hermia.identity.derive import derive_machine_id
from hermia.identity.types import HardwareFacts

SALT = b"\x01" * 32
OTHER = b"\x02" * 32
M1 = HardwareFacts("UUID-1", "Apple M1 Pro", 17179869184, "darwin")


def test_id_is_16_hex_chars_and_deterministic():
    a = derive_machine_id(M1, SALT)
    b = derive_machine_id(M1, SALT)
    assert a.machine_id == b.machine_id
    assert len(a.machine_id) == 16
    assert all(c in "0123456789abcdef" for c in a.machine_id)


def test_different_salt_gives_different_id_for_same_machine():
    assert derive_machine_id(M1, SALT).machine_id != derive_machine_id(M1, OTHER).machine_id


def test_two_identical_models_with_different_uuids_do_not_collide():
    """Two laptops of identical model and memory must never share an id."""
    a = HardwareFacts("UUID-A", "Apple M1 Pro", 17179869184, "darwin")
    b = HardwareFacts("UUID-B", "Apple M1 Pro", 17179869184, "darwin")
    assert derive_machine_id(a, SALT).machine_id != derive_machine_id(b, SALT).machine_id


def test_missing_platform_uuid_yields_null_id_with_reason():
    f = HardwareFacts(None, "Apple M1 Pro", 17179869184, "darwin")
    got = derive_machine_id(f, SALT)
    assert got.machine_id is None
    assert got.basis == "unavailable:no-platform-uuid"


def test_id_changes_when_ram_changes():
    """RAM is entropy in the tuple, so a genuine hardware change is visible."""
    more = HardwareFacts("UUID-1", "Apple M1 Pro", 34359738368, "darwin")
    assert derive_machine_id(more, SALT).machine_id != derive_machine_id(M1, SALT).machine_id


def test_raw_identifiers_never_appear_in_the_result():
    got = derive_machine_id(M1, SALT)
    blob = f"{got.machine_id}{got.basis}{got.os_family}"
    assert "UUID-1" not in blob
    assert "Apple M1 Pro" not in blob
    assert "17179869184" not in blob


def test_basis_records_what_was_measured_on_success():
    assert derive_machine_id(M1, SALT).basis == "measured:platform-uuid+cpu+ram"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/identity/test_derive.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hermia.identity.derive'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Hardware facts + salt -> machine_id. Pure function, no I/O."""
from __future__ import annotations

import hashlib
import hmac
import json

from hermia.identity.types import HardwareFacts, MachineIdentity

ID_HEX_CHARS = 16


def derive_machine_id(facts: HardwareFacts, salt: bytes) -> MachineIdentity:
    """Derive a salted, locally-unique machine id.

    Returns ``machine_id=None`` with an explanatory ``basis`` whenever the
    machine-bound identifier is missing. There is deliberately no partial or
    fallback identity: a hash of CPU+RAM alone would collide across identical
    laptops, which is worse than admitting we do not know.
    """
    if not facts.is_identifiable:
        return MachineIdentity(None, "unavailable:no-platform-uuid", facts.os_family)

    canonical = json.dumps(
        {
            "platform_uuid": facts.platform_uuid,
            "cpu_brand": facts.cpu_brand,
            "ram_bytes": facts.ram_bytes,
            "os_family": facts.os_family,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hmac.new(salt, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return MachineIdentity(
        digest[:ID_HEX_CHARS], "measured:platform-uuid+cpu+ram", facts.os_family
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/identity/test_derive.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hermia/identity/derive.py tests/unit/identity/test_derive.py
git commit -m "feat(identity): salted machine_id derivation, uuid required (hermia-cfqv)"
```

---

## Task 4: Local probe

**Files:**
- Create: `src/hermia/identity/probes.py`
- Test: `tests/unit/identity/test_probes.py`

Platform commands (all read-only):

| OS | platform_uuid | cpu_brand | ram_bytes |
|---|---|---|---|
| macOS | `ioreg -rd1 -c IOPlatformExpertDevice` → `IOPlatformUUID` | `sysctl -n machdep.cpu.brand_string` | `sysctl -n hw.memsize` |
| Linux | `/etc/machine-id`, else `/sys/class/dmi/id/product_uuid` | `model name` in `/proc/cpuinfo` | `MemTotal` in `/proc/meminfo` (kB → bytes) |
| Windows | `reg query HKLM\SOFTWARE\Microsoft\Cryptography /v MachineGuid` | `PROCESSOR_IDENTIFIER` env | `wmic ComputerSystem get TotalPhysicalMemory` |

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch
from hermia.identity.probes import LocalProbe


def test_macos_probe_parses_ioreg_and_sysctl():
    ioreg = '  "IOPlatformUUID" = "ABC-123"\n'
    with patch("hermia.identity.probes._run") as run:
        run.side_effect = lambda cmd, **kw: {
            "ioreg": ioreg, "machdep.cpu.brand_string": "Apple M1 Pro", "hw.memsize": "17179869184",
        }[next(k for k in ("ioreg", "machdep.cpu.brand_string", "hw.memsize") if k in " ".join(cmd))]
        f = LocalProbe(os_family="darwin").probe()
    assert f.platform_uuid == "ABC-123"
    assert f.cpu_brand == "Apple M1 Pro"
    assert f.ram_bytes == 17179869184


def test_probe_failure_yields_none_not_a_guess():
    with patch("hermia.identity.probes._run", return_value=None):
        f = LocalProbe(os_family="darwin").probe()
    assert f.platform_uuid is None
    assert not f.is_identifiable
    assert "platform_uuid" in f.unavailable


def test_unsupported_os_reports_unavailable_rather_than_raising():
    f = LocalProbe(os_family="plan9").probe()
    assert f.platform_uuid is None
    assert f.os_family == "plan9"


def test_ram_bytes_is_never_zero_when_unmeasured():
    """0 would read as a real measurement of a 0-byte machine."""
    with patch("hermia.identity.probes._run", return_value=""):
        f = LocalProbe(os_family="darwin").probe()
    assert f.ram_bytes is None


def test_linux_meminfo_kb_is_converted_to_bytes():
    with patch("hermia.identity.probes._read_text") as rt:
        rt.side_effect = lambda p: {
            "/etc/machine-id": "deadbeef\n",
            "/proc/cpuinfo": "model name\t: AMD Ryzen 9\n",
            "/proc/meminfo": "MemTotal:       32768000 kB\n",
        }.get(str(p))
        f = LocalProbe(os_family="linux").probe()
    assert f.ram_bytes == 32768000 * 1024
    assert f.cpu_brand == "AMD Ryzen 9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/identity/test_probes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hermia.identity.probes'`

- [ ] **Step 3: Write the implementation**

Implement `_run(cmd) -> str | None` (subprocess, short timeout, returns `None` on any failure — never raises), `_read_text(path) -> str | None`, and `LocalProbe` with `probe()` dispatching on `os_family` (defaulting to `platform.system().lower()`). Every extractor returns `None` on absent/unparseable input and appends the field name to `unavailable`. **No `except: pass` that yields a value** — a failed measurement must be `None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/identity/test_probes.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hermia/identity/probes.py tests/unit/identity/test_probes.py
git commit -m "feat(identity): cross-platform local hardware probe (hermia-cfqv)"
```

---

## Task 5: Cross-check ledger — the high-value part

This is the check that would have caught `hermia-fqod` **at dispatch time** instead of a month later during analysis.

**Files:**
- Create: `src/hermia/identity/crosscheck.py`
- Test: `tests/unit/identity/test_crosscheck.py`

- [ ] **Step 1: Write the failing test**

```python
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


def test_stable_pairing_repeated_many_times_stays_silent(tmp_path):
    led = tmp_path / "ledger.json"
    for _ in range(5):
        record_observation("host-d", "ffff555555555555", led)
        assert check_identity_consistency("host-d", "ffff555555555555", led) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/identity/test_crosscheck.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'hermia.identity.crosscheck'`

- [ ] **Step 3: Write the implementation**

`IdentityWarning` frozen dataclass with `kind: str` and `message: str`. Ledger is JSON at `~/.hermia/machine_ledger.json`: `{"label_to_id": {...}, "id_to_label": {...}}`. `check_identity_consistency(label, machine_id, path)` returns `[]` when `machine_id is None` or the ledger is unreadable/corrupt; otherwise emits `label_moved_machine` and/or `machine_renamed`. `record_observation` writes both directions. **Warnings only — never raise, never block a run.**

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/identity/test_crosscheck.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/hermia/identity/crosscheck.py tests/unit/identity/test_crosscheck.py
git commit -m "feat(identity): label/machine cross-check ledger (hermia-cfqv)"
```

---

## Task 6: Anonymized-export pseudonyms

**Files:**
- Modify: `src/hermia/sink/anonymize.py`
- Test: `tests/unit/test_anonymize.py`

- [ ] **Step 1: Write the failing test**

```python
from hermia.sink.anonymize import SUBMIT_WHITELIST, assign_machine_pseudonyms


def test_machine_id_is_not_whitelisted():
    """Default-deny must keep the salted hash out of submissions."""
    assert "machine_id" not in SUBMIT_WHITELIST
    assert "machine_id_basis" not in SUBMIT_WHITELIST


def test_pseudonyms_are_stable_and_ordered_by_first_appearance():
    rows = [{"machine_id": "bbbb"}, {"machine_id": "aaaa"}, {"machine_id": "bbbb"}]
    got = assign_machine_pseudonyms(rows)
    assert [r["machine_pseudonym"] for r in got] == ["node-a", "node-b", "node-a"]


def test_null_machine_id_gets_null_pseudonym_not_a_node_name():
    got = assign_machine_pseudonyms([{"machine_id": None}])
    assert got[0]["machine_pseudonym"] is None


def test_original_machine_id_is_removed_from_the_output():
    got = assign_machine_pseudonyms([{"machine_id": "aaaa"}])
    assert "machine_id" not in got[0]


def test_input_rows_are_not_mutated():
    rows = [{"machine_id": "aaaa"}]
    assign_machine_pseudonyms(rows)
    assert rows[0]["machine_id"] == "aaaa"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_anonymize.py -q -k pseudonym`
Expected: FAIL — `ImportError: cannot import name 'assign_machine_pseudonyms'`

- [ ] **Step 3: Write the implementation**

Add `assign_machine_pseudonyms(rows)` returning **new** dicts: replace `machine_id` with `machine_pseudonym` (`node-a`, `node-b`, … `node-z`, `node-aa`, …) assigned in first-appearance order within the dataset. `None` in → `None` out. Neither the salt nor the mapping is ever written to output. Do **not** touch `SUBMIT_WHITELIST`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_anonymize.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hermia/sink/anonymize.py tests/unit/test_anonymize.py
git commit -m "feat(identity): pseudonymise machine_id on anonymized export (hermia-cfqv)"
```

---

## Task 7: Public API and full-suite green

**Files:**
- Create: `src/hermia/identity/__init__.py`
- Test: `tests/unit/identity/test_public_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_public_api_exports():
    import hermia.identity as ident
    for name in (
        "HardwareFacts", "MachineIdentity", "HardwareProbe", "LocalProbe",
        "derive_machine_id", "load_or_create_salt", "check_identity_consistency",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/identity/test_public_api.py -q`
Expected: FAIL — missing exports

- [ ] **Step 3: Write `__init__.py`** re-exporting the seven names with `__all__`.

- [ ] **Step 4: Verify the whole gate**

```bash
.venv/bin/ruff check src/
.venv/bin/mypy src/
.venv/bin/pytest -q -k 'not test_detect_gpu'
```
Expected: ruff clean; mypy clean; **2025 + new tests passed, 9 deselected**. The 9 deselected are the known macOS GPU-detection failures (`hermia-2ess`) — pre-existing on `dev`, unrelated to this work.

- [ ] **Step 5: Commit**

```bash
git add src/hermia/identity/__init__.py tests/unit/identity/test_public_api.py
git commit -m "feat(identity): public API for machine identity core (hermia-cfqv)"
```

---

## Self-Review

**Spec coverage.** Bead points 1–4 → Tasks 1–4 (tuple, HMAC+salt, salt storage, label kept separate as a pure convenience with no code dependency). Point 5 (anonymized export → pseudonyms) → Task 6. Point 6 (runtime cross-check) → Task 5. "EXCLUDE MAC" → enforced by omission from `HardwareFacts` and asserted by `test_raw_identifiers_never_appear_in_the_result` plus the absence of any MAC field. "Explicit null, never a guess" → tested in Tasks 1, 3, 4, 5, 6.

**Gap accepted deliberately:** nothing stamps a row. Stated under Non-Goals with the reason; without the transport decision, any row stamp would be wrong for fleet runs.

**Placeholder scan.** Tasks 4, 5 and 6 give prose implementation notes rather than full code, because each is mechanical given the fully-specified tests above them and the exact platform commands in the Task 4 table. Every test body is complete and runnable.

**Type consistency.** `HardwareFacts(platform_uuid, cpu_brand, ram_bytes, os_family, unavailable)`, `MachineIdentity(machine_id, basis, os_family)`, `derive_machine_id(facts, salt)`, `load_or_create_salt(path)`, `check_identity_consistency(label, machine_id, path)`, `record_observation(label, machine_id, path)`, `assign_machine_pseudonyms(rows)` — consistent across all tasks.
