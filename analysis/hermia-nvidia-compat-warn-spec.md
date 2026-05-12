# hermia-nvidia-compat-warn — NVIDIA compute capability warning

## What this bead does

When Hermia detects an NVIDIA GPU with compute capability < 6.0 (Maxwell / Kepler and
older), it shows a visible warning on the SelectionScreen. Without this, a user on an
older card sees no indication that Ollama may silently fail to use the GPU — the first
sign is 500 errors during inference.

Discovered empirically: GTX 980 (sm 5.2) causes Ollama 0.22.1 to crash on model load
under CUDA 12.2. The runner process terminates without a user-visible error in Hermia.

## Threshold

`compute_cap < 6.0` — Pascal (GTX 10xx, sm 6.x) is the oldest generation with reliable
Ollama/llama.cpp CUDA support. Maxwell (sm 5.x) and Kepler (sm 3.x) are in the warning
zone. Threshold is a named constant `_NVIDIA_MIN_SUPPORTED_COMPUTE = 6.0` in `metrics.py`
for easy future adjustment.

## Changes

### `src/hermia/metrics.py`

- `_detect_nvidia()` adds `compute_cap` to its query:
  ```
  nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader,nounits
  ```
  Returns `(found, name, vram_total_gb, compute_cap: float)` — `0.0` on failure.

- `detect_gpu()` includes `compute_cap: float` in the returned dict for all vendors
  (0.0 for non-NVIDIA). Existing callers are unaffected — new key added, nothing removed.

- Module-level constant: `_NVIDIA_MIN_SUPPORTED_COMPUTE: float = 6.0`

### `src/hermia/screens.py`

`SelectionScreen` — the GPU label at line 149 gains an optional warning suffix:

```
GPU: NVIDIA GeForce GTX 980  (4.0 GB VRAM)  ⚠ sm 5.2 — Ollama may fall back to CPU (requires sm 6.0+)
```

Logic:
```python
warn = ""
if vendor == "nvidia":
    cc = gpu.get("compute_cap", 0.0)
    if 0.0 < cc < _NVIDIA_MIN_SUPPORTED_COMPUTE:
        warn = f"  ⚠ sm {cc} — Ollama may fall back to CPU (requires sm 6.0+)"
gpu_label = f"GPU: {gpu['card']}  ({gpu['vram_total_gb']:.1f} GB {mem_label}){warn}"
```

`_NVIDIA_MIN_SUPPORTED_COMPUTE` is imported from `metrics`.

## Permitted scope

- `src/hermia/metrics.py`
- `src/hermia/screens.py`
- `tests/unit/test_metrics.py`
- `tests/unit/test_screens.py`

## Acceptance criteria

1. `_detect_nvidia()` queries `compute_cap` via `nvidia-smi`; returns it as a float (e.g. `5.2`)
2. `detect_gpu()` returns dict includes `compute_cap: float` for all vendors
3. `_NVIDIA_MIN_SUPPORTED_COMPUTE = 6.0` defined as a module constant
4. SelectionScreen GPU label shows warning suffix when `vendor == "nvidia"` and `0.0 < compute_cap < 6.0`
5. No warning shown for sm 6.0+ cards (RTX/GTX 10xx and newer)
6. No warning shown for non-NVIDIA vendors
7. No warning shown if `compute_cap == 0.0` (nvidia-smi failed to return it — fail silent)
8. Unit tests:
   - `test_detect_nvidia_returns_compute_cap` — mocked nvidia-smi returning `"GTX 980, 4096, 5.2"` → `compute_cap == 5.2`
   - `test_detect_nvidia_compute_cap_missing` — mocked nvidia-smi returning only 2 fields → `compute_cap == 0.0` (no crash)
   - `test_detect_gpu_nvidia_includes_compute_cap` — `detect_gpu()` dict has `compute_cap` key
   - `test_selection_screen_nvidia_old_gpu_warning` — Pilot test: gpu_info with sm 5.2 → label contains "⚠"
   - `test_selection_screen_nvidia_new_gpu_no_warning` — gpu_info with sm 8.9 → label does not contain "⚠"
   - `test_selection_screen_non_nvidia_no_warning` — amd vendor → no "⚠"

## Estimate

0.5 days

## Why

Silent failure mode for a class of hardware that real users own. The warning is cheap;
the confusion it prevents is not.
