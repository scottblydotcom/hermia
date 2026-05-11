# Spec: hermia-tun — TUI test coverage via Textual Pilot

**Bead:** hermia-tun  
**Priority:** P0 (launch-blocking)  
**Status:** Complete

---

## 1. What this bead does

Adds Textual Pilot tests for `screens.py`, raising statement coverage from **31% → ≥ 70%**.

No production code changes. All changes are in `tests/unit/test_screens_pilot.py`
(new file) and `tests/unit/test_screens.py` (one additional pure-function test).

---

## 2. Coverage gap (as of hermia-0ws merge)

```
src/hermia/screens.py   234 stmts   162 missed   31%

Missing:
  61            _backfill_aggregates empty-list early return
  100-101       SelectionScreen.__init__
  104-131       SelectionScreen.compose
  134-143       SelectionScreen.on_button_pressed
  146-160       SelectionScreen._launch_runner
  190-201       RunnerScreen.compose
  204-205       RunnerScreen.on_mount
  208-217       RunnerScreen._refresh_metrics
  220           RunnerScreen.action_go_back
  224-378       RunnerScreen.run_evals (worker thread)
```

Target: 234 × 0.70 = 164 stmts covered (need ~92 more).

---

## 3. Permitted scope

| File | Change type |
|---|---|
| `tests/unit/test_screens.py` | Add one test (line 61 branch) |
| `tests/unit/test_screens_pilot.py` | New file — all Pilot tests |

Do **not** touch any `src/` file.

---

## 4. Test fixture design

### 4.1 Imports and dependencies

```python
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App

from hermia.preflight import ModelCheck, PreflightReport
from hermia.screens import RunnerScreen, SelectionScreen
from hermia.schemas import TEST_IDS
```

### 4.2 `_make_test_app` — factory helper

Create a subclass of `App` (not `EvalApp`) to avoid calling `get_available_models()`
and `detect_gpu()` during `__init__`. Inject controlled `model_list` and `gpu_info`.

```python
FAKE_MODELS = [
    {"name": "qwen2.5:7b", "size": 4 * 1024**3},
    {"name": "llama3:8b",  "size": 5 * 1024**3},
]

GPU_FOUND = {
    "found": True,
    "card": "RTX 4090",
    "vendor": "nvidia",
    "vram_total_gb": 24.0,
    "vram_used_gb": 0.5,
}

GPU_NOT_FOUND = {"found": False}


def _make_test_app(
    gpu_info: dict | None = None,
    model_list: list | None = None,
    fleet_mode: bool = False,
    repeat: int = 1,
) -> App:
    """Return an App instance that pushes SelectionScreen on mount."""

    class _TestApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.model_list = model_list if model_list is not None else FAKE_MODELS
            self.gpu_info = gpu_info if gpu_info is not None else GPU_FOUND
            self.fleet_mode = fleet_mode
            self._repeat = repeat

        def on_mount(self) -> None:
            self.push_screen(SelectionScreen(repeat=self._repeat))

    return _TestApp()
```

### 4.3 `fake_preflight_report` — helper for `run_evals` mocking

```python
def _fake_preflight_report(
    runnable: list[str] | None = None,
    skipped: list[str] | None = None,
) -> PreflightReport:
    models = []
    for name in (runnable or ["qwen2.5:7b"]):
        models.append(ModelCheck(
            name=name, size_gb=4.0,
            fits_total_vram=True, fits_current_vram=True,
            fits_ram=True, skip=False,
        ))
    for name in (skipped or []):
        models.append(ModelCheck(
            name=name, size_gb=20.0,
            fits_total_vram=False, fits_current_vram=False,
            fits_ram=False, skip=True, reason="Too large",
        ))
    return PreflightReport(
        vram_total_gb=16.0, vram_used_gb=0.5, vram_available_gb=15.5,
        ram_total_gb=32.0, ram_available_gb=20.0,
        disk_free_gb=100.0, disk_ok=True,
        models=models,
    )


def _fake_run_test_result(model: str = "qwen2.5:7b") -> dict:
    return {
        "model": model,
        "test_id": "tool-calling-basic",
        "json_valid": True,
        "schema_compliant": True,
        "tokens_per_sec": 55.0,
        "peak_gpu_pct": 80.0,
        "peak_vram_used_gb": 3.5,
        "peak_cpu_pct": 10.0,
        "output_preview": "",
        "run_index": 1,
        "is_cold": True,
    }
```

---

## 5. Test matrix

All Pilot tests are `async def` and use `pytest.mark.asyncio` (or equivalent — use whatever async test runner is already configured in `pyproject.toml`).

### 5.1 Pure-function gap (add to `test_screens.py`)

| Test | Target | Assertion |
|---|---|---|
| `test_backfill_aggregates_empty_list` | line 61 | `_backfill_aggregates([])` returns without error; list still empty |

### 5.2 SelectionScreen — compose and GPU label (covers lines 100-131)

These tests only mount the app; no button clicks required.

| Test | Setup | Assertion |
|---|---|---|
| `test_selection_screen_model_checkboxes_rendered` | GPU_FOUND, FAKE_MODELS | One checkbox per model; IDs match `model_qwen2_5_7b` and `model_llama3_8b` |
| `test_selection_screen_test_checkboxes_rendered` | GPU_FOUND, FAKE_MODELS | One checkbox per TEST_IDS entry; all checked by default |
| `test_selection_screen_gpu_found_label` | GPU_FOUND | `#gpu-info` label text contains "RTX 4090" and "24.0" |
| `test_selection_screen_gpu_not_found_label` | GPU_NOT_FOUND | `#gpu-info` label text contains "not detected" |
| `test_selection_screen_repeat_stored` | repeat=3 | `pilot.app.screen.repeat == 3` after mount |

### 5.3 SelectionScreen — button handlers (covers lines 134-160)

| Test | Action | Assertion |
|---|---|---|
| `test_select_all_models_button` | Uncheck first model, click `#all_models` | Both model checkboxes are `True` |
| `test_select_all_tests_button` | Uncheck first TEST_IDS checkbox, click `#all_tests` | All test checkboxes are `True` |
| `test_launch_no_models_selected` | Uncheck all model checkboxes, click `#run_btn` | `#status` label text is non-empty (error message shown) |
| `test_launch_no_tests_selected` | Uncheck all test checkboxes, click `#run_btn` | `#status` label text is non-empty |
| `test_launch_pushes_runner_screen` | All defaults, mock `run_evals` as no-op, click `#run_btn` | `isinstance(pilot.app.screen, RunnerScreen)` is True |

**Mocking `run_evals` to no-op** (for `test_launch_pushes_runner_screen`):

```python
with patch("hermia.screens.RunnerScreen.run_evals"):
    async with _make_test_app().run_test() as pilot:
        await pilot.pause()
        await pilot.click("#run_btn")
        await pilot.pause()
        assert isinstance(pilot.app.screen, RunnerScreen)
```

### 5.4 RunnerScreen — compose, mount, metrics, back (covers lines 190-220)

For these tests, push `RunnerScreen` directly (no `SelectionScreen`):

```python
class _RunnerTestApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.model_list = FAKE_MODELS
        self.gpu_info = GPU_FOUND
        self.fleet_mode = False

    def on_mount(self) -> None:
        # Patch run_evals so the worker doesn't fire real Ollama calls
        with patch.object(RunnerScreen, "run_evals"):
            self.push_screen(
                RunnerScreen(["qwen2.5:7b"], ["tool-calling-basic"], repeat=1)
            )
```

**Note:** `patch.object` inside `on_mount` is not valid — the patch must wrap the `run_test` call. Use fixture-level patching instead (see §5.5 for the correct pattern).

| Test | Target | Assertion |
|---|---|---|
| `test_runner_screen_widgets_present` | lines 190-201 | `#metrics-bar`, `#log-content`, `#summary-content`, `ProgressBar` all exist in DOM |
| `test_runner_screen_progress_total` | line 196 | `ProgressBar.total == 2` when 2 models × 1 test × 1 repeat |
| `test_runner_screen_metrics_bar_no_data` | line 209-210 | On mount with no sampler data, `#metrics-bar` still displays without error |
| `test_runner_screen_metrics_bar_with_data` | lines 211-217 | Inject fake `MetricsSampler.latest` dict; tick `_refresh_metrics()`; `#metrics-bar` text contains "CPU" |
| `test_runner_screen_go_back` | line 220 | Press "b"; `isinstance(pilot.app.screen, SelectionScreen)` is True |

**`test_runner_screen_go_back` setup:** App pushes `SelectionScreen` first, then `RunnerScreen` on top (standard nav stack). Pressing "b" pops back to `SelectionScreen`.

**`test_runner_screen_metrics_bar_with_data` approach:**

```python
fake_metrics = {
    "cpu_pct": 25.0, "ram_used_gb": 8.0, "ram_total_gb": 32.0,
    "gpu_pct": 60.0, "vram_used_gb": 3.0, "vram_total_gb": 16.0,
}
# After mounting RunnerScreen, access it and override the sampler's latest property:
screen = pilot.app.query_one(RunnerScreen)
screen._live_sampler = MagicMock()
screen._live_sampler.latest = fake_metrics
screen._refresh_metrics()
await pilot.pause()
bar_text = pilot.app.query_one("#metrics-bar").renderable
assert "CPU" in str(bar_text)
```

### 5.5 RunnerScreen.run_evals — mocked integration (covers lines 224-378)

**Goal:** Execute the full worker body with all Ollama-touching callsites mocked. One async test that covers the happy path is sufficient for the coverage target. Add a second for the no-runnable-models branch.

**Fixture — patch targets** (all in `hermia.screens` namespace):

| Symbol | Mock return value |
|---|---|
| `hermia.screens.run_preflight` | `_fake_preflight_report(runnable=["qwen2.5:7b"])` |
| `hermia.screens.open_run` | `(Path("/tmp/hermia_test.jsonl"), Path("/tmp/hermia_test.csv"))` |
| `hermia.screens.load_tests` | `[{"id": "tool-calling-basic", "prompt": "p", "system": "s"}]` |
| `hermia.screens.get_model_size_gb` | `4.0` |
| `hermia.screens.unload_model` | no-op lambda |
| `hermia.screens.prewarm_timed` | `(1.0, 1.0, 2.0)` |
| `hermia.screens.run_test` | `_fake_run_test_result()` |
| `hermia.screens.append_result` | no-op lambda |
| `hermia.screens.patch_results` | no-op lambda |
| `hermia.screens.time.sleep` | no-op lambda |

Use `unittest.mock.patch` as context managers (or `@patch` decorators). Stack all patches before the `run_test()` context. Example structure:

```python
@pytest.mark.asyncio
async def test_run_evals_happy_path() -> None:
    with (
        patch("hermia.screens.run_preflight", return_value=_fake_preflight_report()),
        patch("hermia.screens.open_run", return_value=(Path("/tmp/a.jsonl"), Path("/tmp/a.csv"))),
        patch("hermia.screens.load_tests", return_value=[{"id": "tool-calling-basic", "prompt": "p", "system": "s"}]),
        patch("hermia.screens.get_model_size_gb", return_value=4.0),
        patch("hermia.screens.unload_model"),
        patch("hermia.screens.prewarm_timed", return_value=(1.0, 1.0, 2.0)),
        patch("hermia.screens.run_test", return_value=_fake_run_test_result()),
        patch("hermia.screens.append_result"),
        patch("hermia.screens.patch_results"),
        patch("hermia.screens.time") as mock_time,  # suppress sleep(1)
    ):
        mock_time.sleep = lambda *a: None

        app = _RunnerDirectApp()  # pushes RunnerScreen with 1 model, 1 test
        async with app.run_test(size=(120, 40)) as pilot:
            # Wait for the worker to complete (poll summary content)
            for _ in range(30):
                await pilot.pause(delay=0.1)
                summary = str(pilot.app.query_one("#summary-content").renderable)
                if "EVAL SUMMARY" in summary:
                    break

        assert "EVAL SUMMARY" in summary
        assert "qwen2.5:7b" in summary
```

`_RunnerDirectApp` is a helper `App` subclass that skips `SelectionScreen` and mounts `RunnerScreen` directly:

```python
class _RunnerDirectApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.model_list = [{"name": "qwen2.5:7b", "size": 4 * 1024**3}]
        self.gpu_info = GPU_FOUND
        self.fleet_mode = False

    def on_mount(self) -> None:
        self.push_screen(
            RunnerScreen(["qwen2.5:7b"], ["tool-calling-basic"], repeat=1)
        )
```

**Additional run_evals tests:**

| Test | Preflight setup | Assertion |
|---|---|---|
| `test_run_evals_no_runnable_models` | `runnable=[]` | `#log-content` contains "No models can run" |
| `test_run_evals_skipped_model_logged` | `runnable=["qwen2.5:7b"], skipped=["llama3:8b"]` | `#log-content` contains "Skipping" |

---

## 6. Async test runner

Check `pyproject.toml` for the current async test configuration. If `asyncio_mode = "auto"` is already set (or `pytest-anyio` / `anyio` is configured), use the existing convention. If not, `pytest-asyncio` with `@pytest.mark.asyncio` is the fallback.

Do **not** add a new test dependency if async support is already present.

---

## 7. Coverage acceptance criterion

Run:

```bash
pytest tests/unit/test_screens.py tests/unit/test_screens_pilot.py \
  --cov=hermia.screens --cov-report=term-missing
```

Pass condition: `screens.py` coverage ≥ 70%. CI will enforce this via the existing `pytest --cov` step.

---

## 8. What NOT to do

- Do not write tests that spin up a real Ollama instance or hit the network.
- Do not import `EvalApp` directly in tests — use the `_TestApp` / `_RunnerDirectApp` helpers.
- Do not add `time.sleep` calls in tests — mock `hermia.screens.time`.
- Do not test CSS rendering or visual layout — only widget existence and text content.
- Do not add new dependencies to `pyproject.toml` without checking if one already covers the need.
