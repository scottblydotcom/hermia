# hermia-3lu — TUI: mode-aware display + host identity

## What this bead does

Two related gaps in the TUI, fixed together since they touch the same area of `screens.py`:

1. **Mode badge** — user cannot tell whether they are running LOCAL or FLEET mode without checking the process flags
2. **Host identity** — in fleet mode, there is no indication of which remote machine is being evaluated; caused real confusion during fleet setup (2026-05-12)

## Acceptance criteria

### Header / status bar
- `LOCAL` badge shown when `detect_mode()` returns `"local"`
- `FLEET` badge + target host shown when `detect_mode()` returns `"fleet"`
- Fleet host display: show the raw host URL from `HERMIA_HOST` (e.g. `http://192.168.25.50:11434`)
- Resolved hostname shown if DNS resolves (e.g. `→ m3pro`); suppressed gracefully if DNS fails — never block startup

### Metrics panels — fleet mode
- `peak_cpu_pct`, `peak_ram_used_gb`, `peak_gpu_pct`, `peak_vram_used_gb` panels display `—` (not zero, not blank)
- `vram_server_gb` (from `/api/ps`) shown where local VRAM would be, labelled clearly as server VRAM
- Tooltip or label makes clear these are suppressed because they would reflect the eval client, not the inference server

### Metrics panels — local mode
- All panels behave exactly as today — no regression

## Permitted scope
- `src/hermia/screens.py`
- `src/hermia/app.py` (only if needed to pass mode/host into the screen)
- `tests/unit/test_screens.py`

## Tests required
- At least one Pilot test: fleet-mode layout shows `FLEET` badge and `—` in suppressed panels
- At least one Pilot test: local-mode layout shows `LOCAL` badge and live metric values
- DNS resolution failure in fleet mode does not raise — host URL shown without hostname suffix
- Existing Pilot tests must continue to pass

## Implementation notes
- `detect_mode()` is already in `metrics.py` — import and call at screen init
- Host comes from `os.environ.get("HERMIA_HOST", "http://localhost:11434")`
- DNS resolution: `socket.gethostbyaddr(host_ip)` in a try/except; strip port before lookup
- Do not add network calls to the hot path — resolve once at startup, cache the result
- Badge styling: `LOCAL` in green, `FLEET` in yellow — matches Textual's built-in color tokens

## Estimate
0.5 days

## Why
Operators running fleet evals need to know at a glance what they're looking at. The confusion during fleet setup (running against gateway localhost instead of M3 Pro without knowing) is the concrete failure case this fixes.
