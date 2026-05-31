"""Audit retrieval: read JSONL eval results and render a formatted report."""

import html as _html
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from hermia.results import load_jsonl
from hermia.runner import load_tests_all

# ── Spill / fleet-health analysis ─────────────────────────────────────────────

_MIN_ACCEPTABLE_TPS: float = 5.0   # below → DELETE
_BORDERLINE_TPS: float = 9.0       # below → REVIEW


def _dominant_execution_path(group: list[dict[str, Any]]) -> str:
    """Return the dominant execution path for a (host, model) group.

    Uses the ``execution_path`` field when present; falls back to
    ``vram_server_gb`` heuristics for rows written before v0.2.
    """
    known = [
        r["execution_path"]
        for r in group
        if r.get("execution_path") and r["execution_path"] != "unknown"
    ]
    if known:
        return Counter(known).most_common(1)[0][0]
    # Backward compat: derive from vram_server_gb
    vram_vals = [r["vram_server_gb"] for r in group if r.get("vram_server_gb") is not None]
    if not vram_vals:
        return "unknown"
    return "cpu" if sum(vram_vals) / len(vram_vals) == 0.0 else "probable_gpu"


def _spill_verdict(path: str, med_tps: float) -> str:
    if path == "cpu":
        return "DELETE — CPU fallback"
    if med_tps < _MIN_ACCEPTABLE_TPS:
        return f"DELETE — {med_tps:.1f} t/s (< {_MIN_ACCEPTABLE_TPS})"
    if med_tps < _BORDERLINE_TPS:
        return f"REVIEW  — {med_tps:.1f} t/s (borderline)"
    return "KEEP"


def render_spill(rows: list[dict[str, Any]]) -> str:
    """Render a fleet health / VRAM-spill analysis table.

    Groups results by (host_label, model) and emits a KEEP / REVIEW / DELETE
    verdict per group based on execution path, pass rate, and throughput.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        name = r.get("fleet_host_name") or r.get("host", "unknown")
        model = r.get("model", "unknown")
        groups[(name, model)].append(r)

    header = (
        f"{'HOST':<32} {'MODEL':<40} {'N':>4} {'PASS%':>6}"
        f"  {'MED t/s':>8}  {'VRAM GB':>8}  {'PATH':<12}  VERDICT"
    )
    sep = "─" * 130
    lines = [header, sep]

    for (host, model), group in sorted(groups.items()):
        total = len(group)
        passed = sum(1 for r in group if r.get("schema_compliant"))
        pass_pct = 100.0 * passed / total

        tps_vals = [r["tokens_per_sec"] for r in group if r.get("tokens_per_sec")]
        med_tps = sorted(tps_vals)[len(tps_vals) // 2] if tps_vals else 0.0

        vram_vals = [r["vram_server_gb"] for r in group if r.get("vram_server_gb") is not None]
        avg_vram = sum(vram_vals) / len(vram_vals) if vram_vals else 0.0

        path = _dominant_execution_path(group)
        verdict = _spill_verdict(path, med_tps)

        lines.append(
            f"{host:<32.32} {model:<40.40} {total:>4}  {pass_pct:>5.1f}%"
            f"  {med_tps:>8.1f}  {avg_vram:>8.2f}  {path:<12}  {verdict}"
        )

    lines.append("")
    return "\n".join(lines)


def _load_system_prompts() -> dict[str, str]:
    """Return {test_id: system_prompt} from the bundled test dataset."""
    try:
        return {t["id"]: t.get("system") or "" for t in load_tests_all() if "id" in t}
    except (OSError, json.JSONDecodeError):
        return {}


def _iter_rows(source: Path) -> Iterator[dict[str, Any]]:
    """Yield result rows from a JSONL file or all eval_*.jsonl in a directory."""
    if source.is_file():
        yield from load_jsonl(source)
    else:
        for p in sorted(source.glob("eval_*.jsonl")):
            yield from load_jsonl(p)


def _enrich(rows: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield rows, adding raw_system via dataset lookup where absent (backward compat)."""
    sys_map: dict[str, str] | None = None
    for row in rows:
        if "raw_system" not in row:
            if sys_map is None:
                sys_map = _load_system_prompts()
            yield {**row, "raw_system": sys_map.get(str(row.get("test_id", "")), "")}
        else:
            yield row


def render_jsonl(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(r) for r in rows)


def _host_label(rows: list[dict[str, Any]]) -> str:
    """Return a human-readable label for a group of rows sharing a host."""
    name = rows[0].get("fleet_host_name") if rows else None
    host = rows[0].get("host", "") if rows else ""
    if name:
        return f"{name} — {host}"
    return host


def _host_duration(rows: list[dict[str, Any]]) -> str:
    """Return 'Xm Ys' duration string derived from min/max run_timestamp in the group."""
    timestamps = [r["run_timestamp"] for r in rows if r.get("run_timestamp")]
    if len(timestamps) < 2:
        return "—"
    try:
        t_start = datetime.fromisoformat(min(timestamps))
        t_end = datetime.fromisoformat(max(timestamps))
        secs = int((t_end - t_start).total_seconds())
        return f"{secs // 60}m {secs % 60}s"
    except (ValueError, TypeError):
        return "—"


def render_html(rows: list[dict[str, Any]]) -> str:
    # Derive run date from result timestamps for historical accuracy
    first_ts = rows[0].get("run_timestamp") if rows else None
    try:
        run_date = (
            datetime.fromisoformat(first_ts).strftime("%Y-%m-%d")
            if first_ts
            else datetime.now().strftime("%Y-%m-%d")
        )
    except (ValueError, TypeError):
        run_date = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(rows)
    passed = sum(1 for r in rows if r.get("schema_compliant"))

    def esc(v: object) -> str:
        return _html.escape(str(v)) if v is not None else ""

    # Group rows by host URL, preserving order of first appearance
    host_order: list[str] = []
    host_groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        h = r.get("host", "")
        if h not in host_groups:
            host_order.append(h)
            host_groups[h] = []
        host_groups[h].append(r)

    sections: list[str] = []
    for host_url in host_order:
        group = host_groups[host_url]
        label = _host_label(group)
        g_total = len(group)
        g_passed = sum(1 for r in group if r.get("schema_compliant"))
        g_start = min((r["run_timestamp"] for r in group if r.get("run_timestamp")), default="—")
        g_end = max((r["run_timestamp"] for r in group if r.get("run_timestamp")), default="—")
        duration = _host_duration(group)

        host_summary = (
            f"Started: {esc(g_start)} &nbsp;|&nbsp; Finished: {esc(g_end)}"
            f" &nbsp;|&nbsp; Duration: {duration}"
            f" &nbsp;|&nbsp; Passed: {g_passed}/{g_total}"
        )
        sections.append(
            f'<div class="host-header">'
            f'<h2 class="host-title">{esc(label)}</h2>'
            f'<p class="host-meta">{host_summary}</p>'
            f'</div>'
        )

        for r in group:
            if r.get("failure_reason"):
                cls, badge_label = "error", "ERROR"
            elif r.get("schema_compliant"):
                cls, badge_label = "pass", "PASS"
            else:
                cls, badge_label = "fail", "FAIL"

            fence_note = (
                '<span class="fence-note" title="Model wrapped response in markdown fences">'
                ' ⚠ fenced</span>'
                if r.get("had_markdown_fence") else ""
            )
            error_block = (
                f'<p class="err">{esc(r.get("failure_reason"))}</p>'
                if r.get("failure_reason")
                else ""
            )
            sections.append(
                f'<section class="result {cls}">'
                f'<h2>{esc(r.get("model"))} &mdash; {esc(r.get("test_id"))}'
                f' <span class="badge {cls}">{badge_label}</span>{fence_note}</h2>'
                f"<dl>"
                f'<dt>Dimension</dt><dd>{esc(r.get("dimension"))}</dd>'
                f'<dt>Elapsed</dt><dd>{esc(r.get("elapsed_sec"))}s</dd>'
                f'<dt>tok/s</dt><dd>{esc(r.get("tokens_per_sec"))}</dd>'
                f'<dt>Host</dt><dd>{esc(r.get("host"))}</dd>'
                f"</dl>"
                f"{error_block}"
                f"<h3>System Prompt</h3><pre>{esc(r.get('raw_system'))}</pre>"
                f"<h3>User Prompt</h3><pre>{esc(r.get('raw_prompt'))}</pre>"
                f"<h3>Response</h3><pre>{esc(r.get('raw_response'))}</pre>"
                f"</section>"
            )

    css = "\n".join([
        "body{font-family:system-ui,sans-serif;max-width:1200px;"
        "margin:0 auto;padding:1rem;background:#0d1117;color:#e6edf3}",
        "h1{color:#58a6ff}",
        ".summary{background:#161b22;padding:1rem;"
        "border-radius:6px;margin-bottom:2rem}",
        ".host-header{background:#161b22;border-left:4px solid #58a6ff;"
        "padding:1rem 1.5rem;margin:2rem 0 .5rem;border-radius:6px}",
        ".host-title{color:#58a6ff;margin:0 0 .4rem}",
        ".host-meta{margin:0;font-size:.85rem;color:#8b949e}",
        ".result{background:#161b22;border-radius:6px;padding:1.5rem;"
        "margin-bottom:1rem;border-left:4px solid #58a6ff}",
        ".result.pass{border-left-color:#3fb950}",
        ".result.fail{border-left-color:#f85149}",
        ".result.error{border-left-color:#d29922}",
        ".badge{font-size:.75rem;padding:.2rem .5rem;border-radius:4px}",
        ".badge.pass{background:#196c2e;color:#56d364}",
        ".badge.fail{background:#67060c;color:#f85149}",
        ".badge.error{background:#4d2d00;color:#e3b341}",
        ".fence-note{font-size:.75rem;color:#d29922;margin-left:.5rem}",
        "h2{margin-top:0}",
        "h3{color:#8b949e;font-size:.85rem;margin-bottom:.25rem}",
        "pre{background:#0d1117;padding:1rem;border-radius:4px;"
        "overflow-x:auto;white-space:pre-wrap;font-size:.85rem}",
        "dl{display:grid;grid-template-columns:auto 1fr;"
        "gap:.25rem 1rem;margin:.5rem 0 1rem;font-size:.85rem}",
        "dt{color:#8b949e}.err{color:#f85149;font-family:monospace}",
    ])
    summary = (
        f"Date: {run_date} &nbsp;|&nbsp; Generated: {now}"
        f" &nbsp;|&nbsp; Results: {total}"
        f" &nbsp;|&nbsp; Passed: {passed}/{total}"
        f" &nbsp;|&nbsp; Hosts: {len(host_order)}"
    )
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Hermia Audit Report</title>",
        f"<style>\n{css}\n</style>",
        "</head>",
        "<body>",
        "<h1>Hermia Audit Report</h1>",
        f'<div class="summary"><p>{summary}</p></div>',
        *sections,
        "</body>",
        "</html>",
    ])


def run_audit(
    source: Path,
    fmt: str = "jsonl",
    output: Path | None = None,
) -> None:
    """Read JSONL eval results and write a formatted audit to stdout or a file."""
    if fmt == "html":
        rows = list(_enrich(_iter_rows(source)))
        if not rows:
            print(f"hermia: no results found in {source}", file=sys.stderr)
            return
        content = render_html(rows)
        if output is not None:
            output.write_text(content, encoding="utf-8")
        else:
            print(content)
    elif fmt == "spill":
        rows = list(_iter_rows(source))
        if not rows:
            print(f"hermia: no results found in {source}", file=sys.stderr)
            return
        content = render_spill(rows)
        if output is not None:
            output.write_text(content, encoding="utf-8")
        else:
            print(content)
    else:
        count = 0
        if output is not None:
            with output.open("w", encoding="utf-8") as f:
                for row in _enrich(_iter_rows(source)):
                    f.write(json.dumps(row) + "\n")
                    count += 1
        else:
            for row in _enrich(_iter_rows(source)):
                print(json.dumps(row))
                count += 1
        if count == 0:
            print(f"hermia: no results found in {source}", file=sys.stderr)
