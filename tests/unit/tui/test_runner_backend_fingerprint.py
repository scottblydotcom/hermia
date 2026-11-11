"""The TUI's real run path, end to end, against a recording server (hermia-bw1q).

These drive TuiRunner with NO injected run function, so they go through _real_run_test and
run_test exactly as a user's run does, and check what reached the server and the results file.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from hermia.tui.bus import SessionBus
from hermia.tui.runner_backend import TuiRunner
from hermia.tui.state import FleetConfig, Host, ModelChoice
from tests.fixtures.fake_engine_server import fake_engine_server

TOKEN = "fake-tok-SECRET-123"  # noqa: S105  # pragma: allowlist secret
TOKEN_ENV = "HERMIA_TEST_TUI_TOKEN"  # noqa: S105 -- the NAME of an env var
TEST_CASE = {"id": "tool-calling-basic", "prompt": "go", "system": ""}


def _host(url: str, engine: str, *, auth: bool, stack: dict[str, Any] | None = None) -> Host:
    return Host(
        name="h", url=url, engine=engine, auth_header_env=TOKEN_ENV if auth else None,
        models=[ModelChoice(name="m", selected=True)], stack=stack,
    )


def _run_tui(host: Host, repeat: int, results_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Run the real TUI path; return the saved rows and the raw text of the results files."""
    runner = TuiRunner(
        config=FleetConfig(name="f", hosts=[host], repeat=repeat),
        bus=SessionBus(), results_dir=results_dir, _tests_override=[TEST_CASE],
    )

    async def _go() -> None:
        await runner.start()
        assert runner._task is not None
        await runner._task

    asyncio.run(_go())
    files = sorted(results_dir.glob("eval_*.*"))
    text = "\n".join(f.read_text() for f in files)
    rows = [
        json.loads(line)
        for f in files if f.suffix == ".jsonl"
        for line in f.read_text().splitlines() if line.strip()
    ]
    return rows, text


def test_tui_openai_compat_rows_are_stamped_openai_compat_and_never_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    with fake_engine_server() as srv:
        rows, text = _run_tui(_host(srv.url, "openai-compat", auth=True), 1, tmp_path)
    assert len(rows) == 1, rows
    assert rows[0]["failure_reason"] == "", rows[0]["failure_reason"]
    assert rows[0]["stack_fingerprint"]["runtime"]["engine"] == "openai-compat", rows[0]
    assert not [p for p in srv.paths() if p.startswith("/api/")], srv.seen
    assert ("POST", "/v1/chat/completions", f"Bearer {TOKEN}") in srv.seen, srv.seen
    assert TOKEN not in text


def test_tui_ollama_behind_auth_is_probed_once_per_model_with_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    with fake_engine_server() as srv:
        rows, text = _run_tui(_host(srv.url, "ollama", auth=True), 2, tmp_path)
    assert len(rows) == 2, rows
    shows = [s for s in srv.seen if s[1] == "/api/show"]
    assert shows == [("POST", "/api/show", f"Bearer {TOKEN}")], srv.seen
    assert [r["failure_reason"] for r in rows] == ["", ""], rows
    assert [r["vram_server_gb"] for r in rows] == [4.0, 4.0], rows
    assert [r["stack_fingerprint"]["offload"]["execution_path"] for r in rows] == ["gpu", "gpu"]
    assert TOKEN not in text


def test_tui_scheme_less_host_reaches_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with fake_engine_server() as srv:
        bare = srv.url.removeprefix("http://")
        rows, _ = _run_tui(_host(bare, "ollama", auth=False), 1, tmp_path)
    assert ("POST", "/api/chat", None) in srv.seen, srv.seen
    assert rows[0]["failure_reason"] == "", rows[0]["failure_reason"]


def test_tui_declared_stack_reaches_the_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = {"compute_backend": {"type": "cuda"}, "substrate": {"delivery": "bare-metal"}}
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with fake_engine_server() as srv:
        rows, _ = _run_tui(_host(srv.url, "ollama", auth=False, stack=stack), 1, tmp_path)
    fp, prov = rows[0]["stack_fingerprint"], rows[0]["_provenance"]
    assert fp["compute_backend"]["type"] == "cuda", fp["compute_backend"]
    assert fp["substrate"]["delivery"] == "bare-metal", fp["substrate"]
    assert prov["compute_backend.type"] == "declared", prov
