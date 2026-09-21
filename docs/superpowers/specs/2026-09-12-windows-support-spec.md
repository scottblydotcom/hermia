# Native Windows support for Hermia — spec

**Bead:** `hermia-8eh7` — *Native Windows support for hermia (CLI/TUI), not just Windows fleet targets*
**Status:** spec, pre-implementation. **Date:** 2026-09-12. **Base:** `dev` @ `3f4546d`.

Every claim below carries a grade:
**[V]** executed or read directly during this spec pass · **[R]** reported by an investigating
agent, not independently re-run · **[I]** judgment.

---

## 1. The finding that sets the shape of this work

**Hermia is not known to crash on Windows. The risk is that it runs and records wrong data.**

Six independent investigators swept the tree for Windows-hostile constructs. What they did *not*
find is the important part:

| Swept for | Result | Grade |
|---|---|---|
| POSIX-only imports (`pwd`, `grp`, `termios`, `fcntl`, `resource`, `pty`, `os.fork`) | one hit: `fcntl`, in `identity/crosscheck.py`, a module with **no caller in `src/`** | **[V]** |
| `shell=True`, `os.system`, `/bin/sh` | none | **[R]** ×3 sweeps |
| `tempfile` reopened by name, `os.rename` over an existing target, symlinks | none | **[R]** ×3 sweeps |
| CSV written without `newline=""` | none — already correct | **[V]** |
| Byte-exact fixture files without an EOL pin | none — `.gitattributes` already pins them `eol=lf` | **[V]** |

`textual` ships a Windows driver and declares Windows 10/11 support **[R]**. All declared runtime
dependencies have Windows wheels or are pure Python **[R]**.

So this is not a port. It is three separate problems, and only one of them is about running:

1. **Data correctness** — files read without an explicit encoding, and hardware that goes
   undetected. A measurement tool that silently records wrong numbers is worse than one that
   refuses to start.
2. **A test suite that cannot pass on Windows** — assertions about POSIX file modes, and a
   type-check that fails before any test runs.
3. **No claim, no lane, no evidence** — nothing declares support and nothing tests it.

---

## 2. What is now known, and what still is not

### ✅ Phase 0 happened — Scott ran it, 2026-09-12

> "pip install hermia worked on windows. running `hermia` launches the TUI. It doesn't detect
> the gpu on my 7800xt though."

That is the first execution of Hermia on Windows by anyone. It settles the two questions this
spec was built around, and it confirms §1: **it runs, and it records wrong data.**

| Question | Answer | Grade |
|---|---|---|
| Does `pip install` work? | Yes | **[V — Scott]** |
| Does the TUI launch? | Yes | **[V — Scott]** |
| Is the recorded data correct? | **No.** A 16 GB RX 7800 XT is recorded `vendor="none"`, `vram_total_gb=0.0` | **[V — Scott, mechanism read by me]** |

Mechanism, read directly: `_find_amdgpu_dev()` enumerates GPUs with
`glob.glob("/sys/class/drm/card*/device/uevent")` — Linux sysfs. On Windows the glob returns
empty, the Intel branch also fails, and `detect_gpu()` falls through to its terminal dict, which
reports `vram_total_gb: 0.0` — a measurement claim about a card that was never measured. Tracked
as `hermia-j6a8` (*a 16 GB RX 7800 XT is recorded as vendor='none', vram_total_gb=0.0*). **[V]**

This promotes A5 from inferred to observed, and moves W8 up the order.

**And it surfaced a second-order defect the sweep missed entirely.** `submit.py`'s
`compute_unified_memory_gb` carries a deliberate safety net for precisely this failure:

> `# Discrete GPUs do NOT share system RAM. If VRAM detection failed (vram == 0.0), report`
> `# None rather than a misleading system-RAM figure`

The guard is keyed on the vendor being *known* (`nvidia` or `amd`). The Windows failure mode is
the vendor being **unknown**, so the guard never engages, control reaches the final branch, and
the machine submits **total system RAM** as its memory figure. Executed **[V]**:

| Input | Returns |
|---|---|
| `vendor="amd"`, VRAM probe failed | `None` — the guard fires, correctly |
| `vendor="none"`, VRAM probe failed | a float: total system RAM |

So a Windows host does not report "unknown". It reports a plausible number that is the wrong
quantity, and is **indistinguishable from a genuine CPU-only host** — a configuration the README
lists as supported. The existing safety net was built for *known GPU, failed probe*; nobody wrote
one for *GPU not known at all*.

Consequence for W8: the easy half is not sufficient alone. Flipping `vram_total_gb` to `None`
makes `vram > 0.0` raise a `TypeError` at `submit.py:195`, and the `vendor="none"` path returns
system RAM either way. An honest fix needs a third state — **not probed on this platform** —
distinct from both *probed, found nothing* and *no GPU present*. That is a small design question,
not a one-liner, and `submit.py` sits outside the metrics module boundary.

### The install path itself is not clean — two blockers, both hit in the first ten minutes

Neither was predicted by any of the seventeen agents, because both live in the gap between
"the code runs" and "a human can get the code running". **[V — Scott, on hardware]**

| # | What happened | Why the sweep missed it |
|---|---|---|
| I1 | `py` is not recognized. The python.org launcher is absent on Microsoft Store and most winget installs, so every `py -m ...` instruction fails. | The agents read source, not install instructions. |
| I2 | `.venv\Scripts\Activate.ps1` refused: *"running scripts is disabled on this system"* (`UnauthorizedAccess`). PowerShell's default execution policy on Windows client SKUs blocks `.ps1`, including the activator Python itself generates. The venv is created fine; only activation is refused. | Same. The repo's docs describe only the POSIX `source .venv/bin/activate` flow. |

Tracked as `hermia-gbt6` (*the documented venv activation is blocked by default PowerShell
execution policy*).

**Guidance that avoids both, and is better practice regardless:** never activate — invoke by path.

```
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\hermia.exe
```

The path *is* the selection, which also eliminates the wrong-shell/wrong-Python failure mode that
caused I1. **The docs must not instruct `Set-ExecutionPolicy`** — changing a machine's script
execution policy is a security decision belonging to the user, not a step in an install guide.
Offer it as an option they may choose; `cmd.exe` with `activate.bat` is the other.

### ❌ Still unknown

Everything else. One successful launch on one machine is not a supported platform:

- **The TUI beyond launching** — rendering under load, resize, mouse, key delivery, glyph
  fallback, and ConHost as distinct from Windows Terminal.
- **Every encoding defect in Tier A.** Scott's run did not exercise a non-ASCII fleet file or a
  re-grade over a real results file, which is where A1/A2 bite.
- **Non-US-English Windows.** A cp932 or cp437 host fails differently from cp1252.
- **Everything in Tier B**, which is about CI, not about a user's machine.

The remaining Windows claims below are still emulation, documented Win32 semantics, or code
reading — and two independent emulations agreeing is corroboration between two emulations, not
verification. **[V — stated by all agents]**

---

## 3. Severity ranking

Ordered by how the failure presents, worst first. **A crash is safer than a wrong number** — a
crash is self-reporting; a mis-encoded host label propagates into the corpus and is discovered
months later, if ever.

### Tier A — silently wrong (no error, wrong data)

| # | Defect | Where | Grade |
|---|---|---|---|
| A1 | Fleet YAML read with no `encoding=`. Under a non-UTF-8 code page the corrupted value includes the **host label**, which is stamped onto corpus rows and keys the identity ledger — a phantom machine in the data. | `tui/fleet_io.py` (4 sites) | sites **[V]**, consequence **[R]** |
| A2 | Result JSONL read with no `encoding=`, by both the re-grader and the regression reporter. Of 201 committed result files, 91 contain non-ASCII; 83 of those decode *successfully but wrongly* under cp1252 — corrupting the very response text the grader then scores — and 8 raise outright. | `regrade.py`, `regression.py` | sites **[V]**, counts **[V] — re-derived** |
| A3 | Subprocess output decoded with `text=True` and no `encoding=`. Windows console children emit OEM code pages, not ANSI. The call is wrapped in a bare `except Exception: return None`, so a decode failure silently downgrades machine identity instead of reporting. | `identity/probes.py`; 12 subprocess sites in `src/`, none with `encoding=` | sites **[V]**, consequence **[I]** |
| A4 | `_harden()` claims to force owner-only permissions. On Windows `chmod(0o600)` **succeeds** and does nothing to group/other, and the mode argument to `os.open` is discarded. The reported `scope` still says `"install"` — a value whose whole purpose is to assert the file is protected. The `except OSError` never fires, so widening the handler is not the fix. | `identity/salt.py` | code **[V]**, emulation **[R]** ×3 agreeing |
| A5 | No Windows GPU branch. A Windows box with a real GPU reports `gpu_present() == False` and vendor `"none"`, which feeds the submitted `host_class`. The not-found path still reports `vram_total_gb: 0.0` — a measurement claim about a card nobody measured. | `metrics.py` | **[R]** |
| A6 | Three tests simulate an unwritable directory with `chmod(0o500)`, which Windows ignores. Two of them would **pass while testing nothing**. | `test_salt.py`, `test_crosscheck.py` | **[V]** |
| A7 | A fleet name goes into a filename unsanitised, so `qwen3:30b` becomes an NTFS alternate data stream — silently. `config.py` deliberately keeps the fleet name off the filesystem for results; `fleet_io` does not. | `tui/fleet_io.py`, `tui/screens/modals.py` | **[R]** |

### Tier B — breaks outright

| # | Defect | Where | Grade |
|---|---|---|---|
| B1 | `mypy --platform win32 src/` → **5 errors**, all `fcntl` attribute lookups. CI runs `mypy src/`, so a Windows lane dies at type-check before a single test runs. | `identity/crosscheck.py` | **[V] — I ran it** |
| B2 | Unguarded `import fcntl` in a test → `ModuleNotFoundError`, not a skip. | `test_crosscheck.py` | **[V]** |
| B3 | 5 assertions across 4 tests assert a POSIX mode Windows cannot produce. | `test_salt.py` | sites **[V]**, failures **[R]** ×2 |
| B4 | A subprocess test sets `env={"PATH": "/usr/bin:/bin", ...}` with `check=True` — a POSIX path, and it replaces the whole environment (dropping `SystemRoot`). | `test_runner_backend_run_identity.py` | site **[V]**, failure **[I]** |
| B5 | The re-grader raises `UnicodeDecodeError` on 8 of 201 committed result files under cp1252. | `regrade.py` | **[R]** ×2, one executed |
| B6 | The docs-as-tested workflow is bash throughout. | `.github/workflows/docs-as-tested.yml` | **[R]** |

### Tier C — cosmetic

Em-dashes and box-drawing glyphs in `print()` raise `UnicodeEncodeError` only on **redirected**
stdout on an OEM host; a US-English runner goes green regardless **[V/R]**. JSONL written CRLF
(byte-level only; every reader strips) **[R]**. Config under `~/.config` rather than `%APPDATA%`
**[R]**. README's Docker block is POSIX-shell shaped; `docs/getting-started.md` already documents
the workaround, the README does not **[R]**.

#### The two counts, and why a raw sweep overstates them

An independent AST sweep of `src/` returns **21** text file operations without an explicit
encoding and **17** calls carrying `text=` without one. Classified, both shrink to the figures
used above — **9** and **12** **[V, re-derived this pass]**:

| Dropped from the raw count | How many | Why it does not matter on Windows |
|---|---|---|
| Linux sysfs reads (`/sys/class/drm/...`, `uevent`, `mem_info_vram_*`) | 7 | POSIX-only paths; the code never executes on Windows, and the content is ASCII |
| `SearchBar.open()` — a textual widget method | 2 | not a file operation |
| `os.open()` returning a raw fd | 2 | not text mode; encoding does not apply (this is defect A4, not an encoding defect) |
| the `fcntl` lock file | 1 | in a module with no caller |
| `text=` on textual widgets and dataclasses, not `subprocess` | 5 | not a subprocess call |

Recorded because the raw number is the one a future sweep will rediscover, and because this repo
has a logged habit of the reverse error — a reviewer's list being confidently wrong in *either*
direction. Here the smaller, classified number is the correct one.

### Explicitly out of scope, with reasons

- **Windows multi-process ledger locking.** The module it would fix has no caller **[R]**. Decide
  whether to *wire up* the ledger before scheduling a lock for it.
- **Reusing the `hermia-agent` Windows GPU gate.** It is a separate Go module behind a
  `//go:build windows` tag, reaching `pdh.dll` through `unsafe`, and it measures engine-utilisation
  percentages and a gaming boolean — **no VRAM, no vendor, no card name**, which is three of the
  five fields Hermia records **[R]**. Reuse means a rewrite plus a second daemon. Reject.
- **The dead WMI identity branch.** Real, thoughtful, unreached — and built on `wmic`, which
  Windows 11 24H2 removes by default **[R]**. Separate bead, not part of this port.

---

## 4. Phases

Slices are small and independently mergeable. Ordering rule: **anything provable on the existing
macOS/Linux CI goes before anything that needs a Windows runner.**

### Phase 0 — evidence, zero code

**W0 · One human opens Hermia on real Windows.** ✅ **DONE 2026-09-12 (Scott).** Install and TUI
launch both work; the GPU is not detected and VRAM is recorded as 0.0. See §2. The predicted
outcome — "it runs, and the data is subtly wrong" — held, so the ordering below stands, with W8
promoted.
*Still outstanding from W0's original scope, and worth a second short session:* the TUI in ConHost
as well as Windows Terminal, a fleet run against a local Ollama, a re-grade over a real results
file (which is where the Tier A encoding defects would show), and the `machine_id` actually
stamped on a Windows-produced row.

**W0b · Fix the pre-existing red.** ✅ **Done** — `hermia-tqnp` (*the valid-payload strategy could
draw an invalid payload*). A flaky property test must not be present when a new lane arrives, or
the lane wears the blame. **[V]**

### Phase 1 — silently-wrong fixes, provable without Windows

**W1 · Encoding as machinery, not as six edits.** Add `encoding="utf-8"` at every unencoded
text-file site in `src/`, and add the ruff rule that makes the class unable to return.
*Proof:* a round-trip test under a forced non-UTF-8 locale, which runs on today's Linux CI; plus
ruff failing on a deliberately unencoded `open()`.
*Note:* the write side was already accidentally safe — `json.dumps`/`yaml.safe_dump` default to
ASCII **[V]** — so behaviour changes only on read.

**W2 · Subprocess decoding.** Explicit encoding on the 12 `text=True` sites, and narrow the bare
`except Exception` so a decode failure is *recorded as a degradation* rather than returning `None`.
*Open question — see Q3.*

**W3 · Salt permission honesty.** After hardening, verify the mode actually achieved; where
owner-only cannot be expressed, report an honest scope rather than `"install"`.
*Reachability caveat:* only runs when a fleet entry opts into SSH identity **[V]**. *See Q1.*

**W4 · Fleet-name sanitisation.** Reject or slugify characters NTFS cannot store, and the reserved
device names. Needs a read-compatibility path for names already on disk.

### Phase 2 — make a Windows lane possible

**W5 · `mypy --platform win32` clean.** Restructure the `fcntl` uses behind a guard mypy can
follow. *Proof:* `mypy --platform win32 src/` succeeds **and** `--platform darwin` still does.
This is the one hard blocker confirmed by direct execution **[V]**.

**W6 · Skip infrastructure and platform-bound tests.** Three of these should be *fixed* rather
than skipped — the platform-neutral pattern already exists elsewhere in the same file **[R]**. A
`skipif` is a coverage hole that reads as green; count them explicitly. The repo has **zero**
`skipif` markers today **[V]**.

**W7 · The lane.** A **new workflow file**, not a matrix leg in `ci.yml`: adding a matrix renames
the check and would silently orphan any required-check rule pinned to the old name — the same
failure that previously forced the witness ratchet out of `ci.yml` **[R]**. Start advisory. *See Q5.*

### Phase 3 — Windows-correct behaviour

**W8 · GPU/metrics honesty.** ⬆️ **Promoted — this is now an observed defect on real hardware,
not an inferred one** (§2). Split in two, and land the first half first:

- **W8a — stop fabricating.** Report `None` for VRAM that was never measured, matching the
  contract the rest of `metrics.py` adopted in `hermia-dl2e` (*let detect_mode decide locality*).
  This needs no Windows probe and no Windows runner: it makes **every** unprobed host honest
  rather than wrong. Check `submit.py`'s consumer of `vram_total_gb` before flipping the default.
- **W8b — a Windows probe.** Known hazard, to verify before building:
  `Win32_VideoController.AdapterRAM` is a `UInt32` and saturates at 4 GiB, so the obvious CIM
  route would report ~4 GB for Scott's 16 GB card — trading "no number" for "wrong number", which
  is a downgrade by this spec's own ranking. The 64-bit value lives in the registry at
  `HardwareInformation.qwMemorySize`. **[I — not yet verified on hardware; probe commands are
  with Scott.]**

**W9 · Results directory.** `RESULTS_DIR = Path("results")` is cwd-relative and defined twice
**[R]**. Windows amplifies it: a Start-menu or Explorer launch has cwd `C:\Windows\System32`.
Tracked as `hermia-s1s0` (*results directory is cwd-relative*). *See Q4.*

### Phase 4 — packaging and docs, only after W0

**W10 · Declare it.** Add the Windows OS classifier; restructure the README platform table — it
pairs OS with GPU, so the Windows row cannot simply flip to ✅. **This is an external support
claim.** *See Q6.*

**W11 · docs-as-tested Windows leg.** `shell: bash` throughout, Windows user paths, drop the
Homebrew and Docker legs.

---

## 5. Required to run vs. nice to have

| Required before a user can trust Hermia on Windows | Not required for that |
|---|---|
| **W0** — know what actually happens | W5 `mypy` — CI-only, invisible to users |
| **W1** encoding — the fleet file is the user's first input, and the re-grader crashes on real corpus | W6 / W7 — test and lane work, invisible to users |
| **W9** results directory — an Explorer launch writes into `System32` | W8 GPU honesty — affects data quality, not runnability |
| **W10** an honest support claim | W11 docs-as-tested leg |
| **W4** if fleet names carry `:` — model-derived names do | W2 / W3 — reachable only via SSH identity |

**Smallest slice that meets the stated goal ("one human opens Hermia on real Windows"): W0, and it
requires no code at all.**

---

## 6. Open questions — human decisions before code

1. **Salt permissions (W3).** Set an NTFS ACL (new dependency), report an honest degraded scope, or
   document the gap? Today it reports a protected scope while the mechanism is inoperative. Risk
   appetite.
2. **README install extractor (B-adjacent).** Its allowlist deliberately excludes `python`/`py` to
   stop a forked README from executing `python -c` in CI **[V — the comment says so]**. Recommend:
   document Windows install with bare `pip`/`pipx` and never touch the allowlist. Costs nothing.
3. **Decode policy (W2).** `errors="replace"` turns a crash into a silently-wrong string;
   `errors="strict"` plus an explicit degradation record is more honest and noisier. Given this
   project's whole thesis, **recommend strict + recorded degradation** — but it is a call.
4. **Results directory (W9).** Fixing it changes where existing macOS/Linux users' results land.
   Fix globally, or introduce a platform-appropriate default on Windows only?
5. **Lane strength (W7).** Advisory or required? And **nobody queried GitHub branch protection** —
   it is server-side, not in the repo **[R]**. Someone must check what the required check is
   currently pinned to before any rename.
6. **The support claim (W10).** What is the minimum evidence to publish Windows support — one
   manual run, or a green CI lane? This is an external claim and needs the outside-family gate.
7. **Skips vs fixes (W6).** Three tests can be made platform-neutral instead of skipped. Fix all
   three, or accept the coverage hole?
8. **Is the identity ledger being wired up at all?** It is export-only today. If the answer is no,
   close the Windows-locking bead as moot rather than scheduling it.

---

## 7. Coverage — what this spec did not look at

- **Any execution on Windows.** The single largest gap; see §2.
- **The TUI on a Windows terminal** — rendering, resize, mouse, key delivery, glyph fallback. The
  largest untested surface. `textual` was checked at the *installed* version; `pyproject.toml`
  declares a floor with no ceiling, and the floor's Windows parity was not checked **[R]**.
- **Installing on Windows.** Wheel *availability* was read from PyPI metadata **[R]**; nobody
  resolved or installed the dependency graph on Windows, or exercised the console-script shims.
  **No test exercises any entry-point shim as a shim, on any platform** **[R]**.
- **Non-US-English Windows.** Every emulation assumed cp1252; a cp932 or cp437 host fails
  differently, and a US-English lane would not surface it.
- **Long paths (>260 chars), case-insensitivity collisions, `os.replace` over an open destination,
  network/exFAT filesystems.** Named, not tested.
- **Classification of the two encoding lists** was re-derived this pass **[V]**; the *consequence*
  of a mis-decode reaching a corpus row is **[I]** — traced through the code, not observed.
