"""Audit retrieval: read JSONL eval results and render a formatted report."""

import html as _html
import json
import sys
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from hermia.results import load_jsonl
from hermia.runner import load_tests_all


def _load_system_prompts() -> dict[str, str]:
    """Return {test_id: system_prompt} from the bundled test dataset."""
    try:
        return {t["id"]: t.get("system", "") for t in load_tests_all() if "id" in t}
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


def render_html(rows: list[dict[str, Any]]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(rows)
    passed = sum(1 for r in rows if r.get("schema_compliant"))

    def esc(v: object) -> str:
        return _html.escape(str(v)) if v is not None else ""

    cards: list[str] = []
    for r in rows:
        if r.get("failure_reason"):
            cls, label = "error", "ERROR"
        elif r.get("schema_compliant"):
            cls, label = "pass", "PASS"
        else:
            cls, label = "fail", "FAIL"

        error_block = (
            f'<p class="err">{esc(r.get("failure_reason"))}</p>'
            if r.get("failure_reason")
            else ""
        )
        cards.append(
            f'<section class="result {cls}">'
            f'<h2>{esc(r.get("model"))} &mdash; {esc(r.get("test_id"))}'
            f' <span class="badge {cls}">{label}</span></h2>'
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
        ".result{background:#161b22;border-radius:6px;padding:1.5rem;"
        "margin-bottom:1rem;border-left:4px solid #58a6ff}",
        ".result.pass{border-left-color:#3fb950}",
        ".result.fail{border-left-color:#f85149}",
        ".result.error{border-left-color:#d29922}",
        ".badge{font-size:.75rem;padding:.2rem .5rem;border-radius:4px}",
        ".badge.pass{background:#196c2e;color:#56d364}",
        ".badge.fail{background:#67060c;color:#f85149}",
        ".badge.error{background:#4d2d00;color:#e3b341}",
        "h2{margin-top:0}",
        "h3{color:#8b949e;font-size:.85rem;margin-bottom:.25rem}",
        "pre{background:#0d1117;padding:1rem;border-radius:4px;"
        "overflow-x:auto;white-space:pre-wrap;font-size:.85rem}",
        "dl{display:grid;grid-template-columns:auto 1fr;"
        "gap:.25rem 1rem;margin:.5rem 0 1rem;font-size:.85rem}",
        "dt{color:#8b949e}.err{color:#f85149;font-family:monospace}",
    ])
    summary = (
        f"Generated: {now} &nbsp;|&nbsp; Results: {total}"
        f" &nbsp;|&nbsp; Passed: {passed}/{total}"
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
        *cards,
        "</body>",
        "</html>",
    ])


def run_audit(
    source: Path,
    fmt: str = "jsonl",
    output: Path | None = None,
) -> None:
    """Read JSONL eval results and write a formatted audit to stdout or a file."""
    rows = list(_enrich(_iter_rows(source)))
    if not rows:
        print(f"hermia: no results found in {source}", file=sys.stderr)
        return
    content = render_html(rows) if fmt == "html" else render_jsonl(rows)
    if output is not None:
        output.write_text(content, encoding="utf-8")
    else:
        print(content)
