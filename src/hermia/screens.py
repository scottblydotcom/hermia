"""Textual screens: SelectionScreen and RunnerScreen."""

import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Label, ProgressBar, Static

from hermia.metrics import MetricsSampler
from hermia.preflight import run_preflight
from hermia.results import append_result, open_run
from hermia.runner import (
    get_model_size_gb,
    load_tests,
    prewarm_timed,
    run_test,
    unload_model,
)
from hermia.schemas import TEST_IDS


def _sanitize_model_id(name: str) -> str:
    """Normalise a model name for use as a Textual widget ID."""
    return name.replace(":", "_").replace(".", "_")


def _compute_scores(
    results: list[dict[str, Any]],
) -> list[tuple[str, float, float, float, float]]:
    """Aggregate per-model scores from a flat result list.

    Returns list of (model, json_pass_rate, schema_pass_rate, agentic_score, avg_tps)
    sorted descending by agentic_score.
    """
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_model.setdefault(r["model"], []).append(r)
    scored = []
    for model, rs in by_model.items():
        n = len(rs)
        jp = sum(r["json_valid"] for r in rs) / n
        sp = sum(r["schema_compliant"] for r in rs) / n
        ag = (jp * 0.40) + (sp * 0.60)
        tps = sum(r["tokens_per_sec"] for r in rs) / n
        scored.append((model, jp, sp, ag, tps))
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored


PROJECT_ROOT = Path(__file__).parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"


class SelectionScreen(Screen):  # type: ignore[type-arg]
    CSS = """
    SelectionScreen { background: $surface; }
    #layout { height: 1fr; padding: 1 2; }
    #models-panel, #tests-panel {
        width: 1fr; border: solid $primary; padding: 1 2; margin: 0 1;
    }
    .panel-title { text-style: bold; color: $accent; margin-bottom: 1; }
    #buttons { height: 3; align: center middle; margin-top: 1; }
    Button { margin: 0 1; }
    #status { height: 1; content-align: center middle; color: $warning; }
    #gpu-info { height: 1; content-align: center middle; color: $accent; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="layout"):
            with ScrollableContainer(id="models-panel"):
                yield Label("Models", classes="panel-title")
                for m in self.app.model_list:  # type: ignore[attr-defined]
                    name = m["name"]
                    size_gb = m.get("size", 0) / (1024**3)
                    label = f"{name}  ({size_gb:.1f} GB)"
                    model_id = f"model_{_sanitize_model_id(name)}"
                    yield Checkbox(label, value=True, id=model_id)
            with ScrollableContainer(id="tests-panel"):
                yield Label("Tests", classes="panel-title")
                for t in TEST_IDS:
                    yield Checkbox(t, value=True, id=f"test_{t.replace('-', '_')}")
        with Horizontal(id="buttons"):
            yield Button("Select All Models", id="all_models")
            yield Button("Select All Tests", id="all_tests")
            yield Button("Run Selected", id="run_btn", variant="primary")
        gpu = self.app.gpu_info  # type: ignore[attr-defined]
        if gpu["found"]:
            gpu_label = f"GPU: {gpu['card']}  ({gpu['vram_total_gb']:.1f} GB VRAM)"
        else:
            gpu_label = "GPU: no AMD GPU detected — VRAM metrics unavailable"
        yield Label(gpu_label, id="gpu-info")
        yield Label("", id="status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "all_models":
            for m in self.app.model_list:  # type: ignore[attr-defined]
                name = m["name"]
                model_id = f"#model_{_sanitize_model_id(name)}"
                self.query_one(model_id, Checkbox).value = True
        elif event.button.id == "all_tests":
            for t in TEST_IDS:
                self.query_one(f"#test_{t.replace('-', '_')}", Checkbox).value = True
        elif event.button.id == "run_btn":
            self._launch_runner()

    def _launch_runner(self) -> None:
        selected_models = [
            m["name"]
            for m in self.app.model_list  # type: ignore[attr-defined]
            if self.query_one(f"#model_{_sanitize_model_id(m['name'])}", Checkbox).value
        ]
        selected_tests = [
            t for t in TEST_IDS if self.query_one(f"#test_{t.replace('-', '_')}", Checkbox).value
        ]
        if not selected_models:
            self.query_one("#status", Label).update("Select at least one model.")
            return
        if not selected_tests:
            self.query_one("#status", Label).update("Select at least one test.")
            return
        self.app.push_screen(RunnerScreen(selected_models, selected_tests))


class RunnerScreen(Screen):  # type: ignore[type-arg]
    CSS = """
    RunnerScreen { background: $surface; }
    #metrics-bar {
        height: 3; border: solid $primary-darken-2;
        padding: 0 2; margin: 0 2; content-align: left middle; color: $text-muted;
    }
    #log { height: 1fr; border: solid $primary; padding: 1 2; margin: 1 2 0 2; }
    #summary { height: auto; max-height: 16; border: solid $accent; padding: 1 2; margin: 1 2; }
    .pass { color: $success; }
    .fail { color: $error; }
    .warn { color: $warning; }
    .info { color: $text-muted; }
    #progress-bar { margin: 1 2 0 2; }
    """

    BINDINGS = [("b", "go_back", "Back to Selection")]

    def __init__(self, models: list[str], test_ids: list[str]) -> None:
        super().__init__()
        self.models = models
        self.test_ids = test_ids
        self.all_results: list[dict[str, Any]] = []
        self._live_sampler = MetricsSampler()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Waiting to start...", id="metrics-bar")
        yield ProgressBar(
            total=len(self.models) * len(self.test_ids), show_eta=True, id="progress-bar"
        )
        with ScrollableContainer(id="log"):
            yield Static("", id="log-content")
        with ScrollableContainer(id="summary"):
            yield Static("Results will appear here when complete.", id="summary-content")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(2, self._refresh_metrics)
        self.run_evals()

    def _refresh_metrics(self) -> None:
        m = self._live_sampler.latest
        if not m:
            return
        bar = (
            f"CPU {m['cpu_pct']:4.0f}%  "
            f"RAM {m['ram_used_gb']:4.1f}/{m['ram_total_gb']:.0f} GB  "
            f"GPU {m['gpu_pct']:4.0f}%  "
            f"VRAM {m['vram_used_gb']:4.1f}/{m['vram_total_gb']:.1f} GB"
        )
        self.query_one("#metrics-bar", Static).update(bar)

    def action_go_back(self) -> None:
        self.app.pop_screen()

    @work(thread=True)
    def run_evals(self) -> None:
        tests = load_tests(self.test_ids)
        log_lines: list[tuple[str, str]] = []
        sampler = MetricsSampler()
        self._live_sampler = sampler

        def append_log(line: str, style: str = "") -> None:
            log_lines.append((line, style))
            content = "\n".join(f"[{s}]{ln}[/{s}]" if s else ln for ln, s in log_lines[-100:])
            self.app.call_from_thread(self.query_one("#log-content", Static).update, content)

        # ── Preflight ────────────────────────────────────────────────────────
        pf = run_preflight(self.models, self.app.model_list, RESULTS_DIR)  # type: ignore[attr-defined]
        append_log(
            f"Preflight  VRAM {pf.vram_available_gb:.1f}/{pf.vram_total_gb:.1f} GB free  "
            f"RAM {pf.ram_available_gb:.1f}/{pf.ram_total_gb:.1f} GB free  "
            f"Disk {pf.disk_free_gb:.1f} GB free",
            "info",
        )
        for w in pf.warnings:
            style = "fail" if w.startswith("SKIP") or w.startswith("Low disk") else "warn"
            append_log(f"  {w}", style)

        runnable = pf.runnable_models
        if not runnable:
            append_log("No models can run — aborting. Check VRAM and RAM.", "fail")
            return
        if pf.skipped_models:
            append_log(
                f"Skipping: {', '.join(pf.skipped_models)}  |  Running: {', '.join(runnable)}",
                "warn",
            )
        if not pf.disk_ok:
            append_log("Disk space critical — results may not save.", "fail")
        append_log("", "")

        jsonl_path, csv_path = open_run(RESULTS_DIR)
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_host = socket.gethostname()
        append_log(f"Writing results to {jsonl_path.name} (appended after each test)", "info")
        append_log("", "")

        load_stats: dict[str, dict[str, float]] = {}

        for model in runnable:
            model_size_gb = get_model_size_gb(model, self.app.model_list)  # type: ignore[attr-defined]
            append_log(f"\n── {model}  ({model_size_gb:.1f} GB) ──────────────────────", "info")

            append_log("  Unloading previous model from VRAM...", "info")
            unload_model(model)
            time.sleep(1)

            append_log(f"  Cold-loading {model}...", "info")
            sampler.start()
            load_time, vram_before, vram_after = prewarm_timed(model)
            sampler.stop()

            vram_delta = vram_after - vram_before
            load_gbps = model_size_gb / load_time if load_time > 0 else 0
            load_stats[model] = {
                "size_gb": round(model_size_gb, 2),
                "load_time_sec": round(load_time, 2),
                "load_gbps": round(load_gbps, 2),
                "vram_before_gb": round(vram_before, 2),
                "vram_after_gb": round(vram_after, 2),
                "vram_delta_gb": round(vram_delta, 2),
            }
            append_log(
                f"  Loaded in {load_time:.1f}s  |  "
                f"VRAM {vram_before:.1f}→{vram_after:.1f} GB  |  "
                f"{load_gbps:.2f} GB/s",
                "info",
            )

            for test in tests:
                result = run_test(model, test, sampler)
                result["run_id"] = run_id
                result["run_timestamp"] = datetime.now(UTC).isoformat()
                result["host"] = run_host
                self.all_results.append(result)
                append_result(result, jsonl_path, csv_path)

                tps = result["tokens_per_sec"]
                jv = result["json_valid"]
                sc = result["schema_compliant"]
                gpu = result.get("peak_gpu_pct", 0)
                vram = result.get("peak_vram_used_gb", 0)
                cpu = result.get("peak_cpu_pct", 0)

                if jv and sc:
                    icon, style = "✅", "pass"
                elif jv:
                    icon, style = "⚠ ", "warn"
                else:
                    icon, style = "❌", "fail"

                main_line = (
                    f"  {icon} {test['id']:<35} {tps:5.1f} t/s  "
                    f"GPU {gpu:.0f}%  VRAM {vram:.1f}GB  CPU {cpu:.0f}%"
                )
                append_log(main_line, style)
                if style == "fail":
                    preview = result.get("output_preview", "")
                    if preview:
                        append_log(f"       {preview[:80]}", "warn")
                self.app.call_from_thread(self.query_one(ProgressBar).advance, 1)

        scored = _compute_scores(self.all_results)

        lines = ["[bold]EVAL SUMMARY[/bold]\n"]
        lines.append(f"{'Model':<28} {'JSON%':>6} {'Schema%':>8} {'Agentic':>8} {'t/s':>6}")
        lines.append("─" * 62)
        for model, jp, sp, ag, tps in scored:
            lines.append(
                f"{model:<28} {jp * 100:5.0f}%  {sp * 100:6.0f}%  {ag * 100:7.0f}%  {tps:5.1f}"
            )

        lines.append("\n[bold]LOAD BENCHMARKS[/bold]\n")
        lines.append(f"{'Model':<28} {'Size':>6} {'Load':>7} {'GB/s':>6} {'VRAM Δ':>8}")
        lines.append("─" * 62)
        for model in runnable:
            ls = load_stats.get(model, {})
            lines.append(
                f"{model:<28} {ls.get('size_gb', 0):5.1f}G  "
                f"{ls.get('load_time_sec', 0):5.1f}s  "
                f"{ls.get('load_gbps', 0):5.2f}  "
                f"{ls.get('vram_delta_gb', 0):+.2f} GB"
            )

        lines.append(f"\nBest: [bold]{scored[0][0]}[/bold] ({scored[0][3] * 100:.0f}/100)")
        lines.append(f"Saved: {jsonl_path.name}  |  {csv_path.name}")

        self.app.call_from_thread(
            self.query_one("#summary-content", Static).update, "\n".join(lines)
        )
        append_log("\nDone! See summary below.", "pass")
