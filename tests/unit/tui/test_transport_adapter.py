"""Tests for hermia.tui.transport_adapter — engine → transport factory."""
import urllib.error

import pytest

from hermia.tui.state import Host
from hermia.tui.transport_adapter import (
    OllamaProbeTransport,
    OpenAICompatProbeTransport,
    transport_for,
)


class TestTransportFor:
    def test_returns_object_with_list_models(self) -> None:
        host = Host(name="h", url="http://h:11434", engine="ollama")
        tr = transport_for(host)
        assert hasattr(tr, "list_models")

    def test_ollama_engine_returns_ollama_transport(self) -> None:
        host = Host(name="h", url="http://h:11434", engine="ollama")
        tr = transport_for(host)
        assert isinstance(tr, OllamaProbeTransport)

    def test_openai_compat_engine_returns_openai_transport(self) -> None:
        host = Host(name="h", url="http://h:4000", engine="openai-compat")
        tr = transport_for(host)
        assert isinstance(tr, OpenAICompatProbeTransport)

    def test_unknown_engine_falls_back_to_openai_compat(self) -> None:
        # vLLM / SGLang / LiteLLM all speak the OpenAI shape — non-"ollama"
        # falls through to the openai-compat path.
        host = Host(name="h", url="http://h", engine="vllm")
        tr = transport_for(host)
        assert isinstance(tr, OpenAICompatProbeTransport)

    def test_resolves_auth_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_KEY", "secret-value")
        host = Host(
            name="h",
            url="http://h:4000",
            engine="openai-compat",
            auth_header_env="MY_KEY",
        )
        tr = transport_for(host)
        # The adapter stores the resolved bearer header on the transport
        # instance for the probe to use when calling /v1/models.
        assert tr.auth_header == "Bearer secret-value"

    def test_missing_env_var_leaves_auth_none(self, monkeypatch) -> None:
        monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
        host = Host(
            name="h",
            url="http://h:4000",
            engine="openai-compat",
            auth_header_env="NOT_SET_ANYWHERE",
        )
        tr = transport_for(host)
        assert tr.auth_header is None

    def test_no_auth_header_env_leaves_auth_none(self) -> None:
        host = Host(name="h", url="http://h:11434", engine="ollama")
        tr = transport_for(host)
        assert tr.auth_header is None


class TestSSRFGuard:
    """SSRF guard — only http(s) schemes are allowed for probe URLs."""

    def test_file_scheme_raises_url_error(self) -> None:
        host = Host(name="bad", url="file:///etc/passwd", engine="ollama")
        tr = transport_for(host)
        with pytest.raises(urllib.error.URLError, match="Unsupported protocol scheme"):
            tr._fetch_sync("/api/tags")

    def test_ftp_scheme_raises_url_error(self) -> None:
        host = Host(name="bad", url="ftp://example.com", engine="ollama")
        tr = transport_for(host)
        with pytest.raises(urllib.error.URLError, match="Unsupported protocol scheme"):
            tr._fetch_sync("/api/tags")

    def test_bare_host_gets_http_prefix(self) -> None:
        # Schemeless URL (e.g. "localhost:1") gets normalized to http://
        # so the SSRF guard doesn't reject the common typo. Port 1 is the
        # tcpmux service port — reliably unused on any sane dev machine,
        # so urlopen reliably fails with a connection error rather than
        # potentially reaching a live Ollama on 11434.
        host = Host(name="bare", url="127.0.0.1:1", engine="ollama")
        tr = transport_for(host)
        with pytest.raises(urllib.error.URLError) as exc_info:
            tr._fetch_sync("/api/tags")
        # Should fail with a connection error, NOT the scheme rejection.
        assert "Unsupported protocol scheme" not in str(exc_info.value)
