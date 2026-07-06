"""Tests for FingerprintCache — in-memory (host, model) keyed cache."""

from unittest.mock import MagicMock, patch

from hermia.fingerprint.cache import FingerprintCache


def _dummy_fp() -> dict:
    return {"fingerprint_schema_version": 1, "model": {"digest": "sha256:abc"}}


def _dummy_prov() -> dict:
    return {"model.digest": "api"}


def test_cache_miss_calls_probe() -> None:
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe", return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        fp, prov = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                       engine_version="0.6.2")
    mock_probe.assert_called_once_with("http://host:11434", "m1", None, "0.6.2", None, None)
    assert fp["model"]["digest"] == "sha256:abc"


def test_get_or_probe_forwards_auth_headers_to_http_calls() -> None:
    """Auth headers must reach the underlying /api/show + /api/ps requests.

    Regression guard: authenticated fleet hosts (bearer-token gateway) would
    otherwise 401 and the fingerprint would silently null out.
    """
    cache = FingerprintCache()
    auth = {"Authorization": "Bearer sentinel-value"}

    def _ok_get(url, **kwargs):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = (
            {"version": "0.6.2"} if "/api/version" in url else {"models": []}
        )
        return resp

    with patch("hermia.fingerprint.probes.ollama.requests.post") as mock_post, \
         patch("hermia.fingerprint.probes.ollama.requests.get",
               side_effect=_ok_get) as mock_get:
        mock_post.return_value = MagicMock(ok=True, **{"json.return_value": {}})
        cache.get_or_probe("http://host:11434", "m1", declared=None,
                           engine_version="0.6.2", headers=auth)

    assert mock_post.call_args.kwargs["headers"] == auth
    for call_obj in mock_get.call_args_list:
        assert call_obj.kwargs["headers"] == auth


def test_cache_hit_skips_probe() -> None:
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe", return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        fp1, _ = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                     engine_version="0.6.2")
        fp2, _ = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                     engine_version="0.6.2")
    mock_probe.assert_called_once()
    assert fp1 is fp2


def test_cache_different_model_triggers_new_probe() -> None:
    cache = FingerprintCache()

    fp_m1 = {"fingerprint_schema_version": 1, "model": {"digest": "sha256:m1"}}
    fp_m2 = {"fingerprint_schema_version": 1, "model": {"digest": "sha256:m2"}}

    returns = [(fp_m1, {"model.digest": "api"}), (fp_m2, {"model.digest": "api"})]
    with patch.object(cache, "_do_probe", side_effect=returns) as mock_probe:
        r1, _ = cache.get_or_probe("http://host:11434", "m1", declared=None,
                                    engine_version="0.6.2")
        r2, _ = cache.get_or_probe("http://host:11434", "m2", declared=None,
                                    engine_version="0.6.2")
    assert mock_probe.call_count == 2
    assert r1["model"]["digest"] == "sha256:m1"
    assert r2["model"]["digest"] == "sha256:m2"


def test_cache_different_host_triggers_new_probe() -> None:
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe", return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        cache.get_or_probe("http://h1:11434", "m1", declared=None, engine_version="0.6.2")
        cache.get_or_probe("http://h2:11434", "m1", declared=None, engine_version="0.6.2")
    assert mock_probe.call_count == 2


def test_openai_compat_engine_skips_http_probe() -> None:
    """openai-compat hosts must not make /api/show or /api/ps round-trips.

    The probe endpoints are Ollama-specific; openai-compat (vLLM, SGLang,
    LiteLLM, etc.) would 404 them. Dispatch returns honest null fingerprint
    with engine stamped, zero network cost.
    """
    cache = FingerprintCache()
    with patch("hermia.fingerprint.probes.ollama.requests.post") as mock_post, \
         patch("hermia.fingerprint.probes.ollama.requests.get") as mock_get:
        # Fleet path passes engine='openai-compat' but no engine_version (it
        # has no probe to source one from); keep the call shape realistic.
        fp, prov = cache.get_or_probe(
            "http://gateway:4000", "qwen3-coder:30b", declared=None,
            engine="openai-compat",
        )
    mock_post.assert_not_called()
    mock_get.assert_not_called()
    assert fp["runtime"]["engine"] == "openai-compat"
    assert fp["model"]["digest"] is None
    assert prov["model.digest"] is None
    # Provenance integrity: the engine value came from fleet YAML transport,
    # not an API probe. Must be tagged 'declared', NEVER 'api' — otherwise
    # the _provenance audit map lies about its source.
    assert prov["runtime.engine"] == "declared", (
        f"openai-compat engine value is YAML-declared, not API-derived; "
        f"provenance must be 'declared' not {prov['runtime.engine']!r}"
    )
    assert prov["runtime.engine_version"] is None


def test_engine_none_defaults_to_ollama_probe() -> None:
    """Back-compat: callers that don't pass engine (standalone TUI) still probe."""
    cache = FingerprintCache()
    with patch.object(cache, "_probe") as mock_probe:
        mock_probe.probe.return_value = MagicMock(
            digest=None, architecture=None, family=None, parameter_count=None,
            parameter_size=None, quant_method=None, quant_level=None,
            context_length=None, chat_template=None, chat_template_hash=None,
            engine="ollama", engine_version="0.6.2",
            residency_ratio=None, execution_path=None,
        )
        cache.get_or_probe("http://host:11434", "m1", declared=None,
                           engine_version="0.6.2")
    mock_probe.probe.assert_called_once()


def test_engine_in_cache_key_prevents_cross_engine_collision() -> None:
    """Same (host, model) with different engines must probe independently."""
    cache = FingerprintCache()
    with patch.object(cache, "_do_probe",
                      return_value=(_dummy_fp(), _dummy_prov())) as mock_probe:
        cache.get_or_probe("http://h:11434", "m1", declared=None,
                           engine_version="0.6.2", engine="ollama")
        cache.get_or_probe("http://h:11434", "m1", declared=None,
                           engine_version="0.6.2", engine="openai-compat")
    assert mock_probe.call_count == 2
