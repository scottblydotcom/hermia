"""run_test's fingerprint probe must match the transport that ran the test (hermia-bw1q).

run_test asked the FingerprintCache for an engine-less fingerprint, which takes the Ollama path:
GET /api/version, POST /api/show, GET /api/ps. Over an OpenAI-compatible transport those requests
cannot succeed, carried the host's token, and missed the cache fleet.py had primed under
"openai-compat", so they ran on every (host, model).
"""
from __future__ import annotations

from hermia.fingerprint.cache import FingerprintCache
from hermia.metrics import MetricsSampler
from hermia.runner import run_test
from hermia.transport.ollama import OllamaTransport
from hermia.transport.openai_compat import OpenAICompatTransport
from tests.fixtures.fake_engine_server import fake_engine_server

TOKEN = "fake-tok-SECRET-123"  # noqa: S105  # pragma: allowlist secret
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
TEST_CASE = {"id": "tool-calling-basic", "prompt": "go", "system": ""}


def test_run_test_sends_no_ollama_probe_over_an_openai_compat_transport() -> None:
    with fake_engine_server() as srv:
        row = run_test(
            "m", TEST_CASE, MetricsSampler(), host=srv.url, headers=HEADERS,
            transport=OpenAICompatTransport(srv.url, HEADERS), locality="remote",
        )
    assert not [p for p in srv.paths() if p.startswith("/api/")], srv.seen
    assert "/v1/chat/completions" in srv.paths(), srv.seen
    fp, prov = row["stack_fingerprint"], row["_provenance"]
    assert fp["runtime"]["engine"] == "openai-compat", fp["runtime"]
    assert prov["runtime.engine"] == "declared", prov


def test_run_test_hits_a_cache_primed_the_way_fleet_primes_it() -> None:
    """fleet.py primes with engine=transport_type; run_test's own lookup must land on that key."""
    with fake_engine_server() as srv:
        cache = FingerprintCache()
        primed = cache.get_or_probe(
            srv.url, "m", {"compute_backend": {"type": "cuda"}},
            headers=HEADERS, engine="openai-compat",
        )
        row = run_test(
            "m", TEST_CASE, MetricsSampler(), host=srv.url, headers=HEADERS,
            transport=OpenAICompatTransport(srv.url, HEADERS), locality="remote",
            fp_cache=cache,
        )
    assert list(cache._store) == [(srv.url, "m", "openai-compat")], list(cache._store)
    assert row["stack_fingerprint"] == primed[0], row["stack_fingerprint"]
    assert not [p for p in srv.paths() if p.startswith("/api/")], srv.seen


def test_run_test_still_probes_an_ollama_transport_with_its_token() -> None:
    with fake_engine_server() as srv:
        row = run_test(
            "m", TEST_CASE, MetricsSampler(), host=srv.url, headers=HEADERS,
            transport=OllamaTransport(srv.url, HEADERS), locality="remote",
        )
    shows = [s for s in srv.seen if s[1] == "/api/show"]
    assert shows == [("POST", "/api/show", f"Bearer {TOKEN}")], srv.seen
    fp = row["stack_fingerprint"]
    assert fp["runtime"]["engine"] == "ollama", fp["runtime"]
    assert fp["model"]["digest"] == "sha256:abc", fp["model"]
    assert row["failure_reason"] == "", row["failure_reason"]


def test_run_test_passes_the_declared_stack_into_the_fingerprint() -> None:
    declared = {"compute_backend": {"type": "cuda"}, "substrate": {"delivery": "bare-metal"}}
    with fake_engine_server() as srv:
        row = run_test(
            "m", TEST_CASE, MetricsSampler(), host=srv.url, headers=HEADERS,
            transport=OllamaTransport(srv.url, HEADERS), locality="remote",
            declared=declared,
        )
    fp, prov = row["stack_fingerprint"], row["_provenance"]
    assert fp["compute_backend"]["type"] == "cuda", fp["compute_backend"]
    assert fp["substrate"]["delivery"] == "bare-metal", fp["substrate"]
    assert prov["compute_backend.type"] == "declared", prov
