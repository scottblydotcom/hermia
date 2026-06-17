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
    mock_probe.assert_called_once_with("http://host:11434", "m1", None, "0.6.2", None)
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
