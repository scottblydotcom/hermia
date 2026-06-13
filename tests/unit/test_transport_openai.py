from unittest.mock import MagicMock, patch

import pytest

from hermia.transport.base import Transport, TransportError
from hermia.transport.openai_compat import OpenAICompatTransport


def test_generate_posts_to_v1_chat_completions():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        mock_post.assert_called_once_with(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-3.5",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.1
            },
            headers={},
            timeout=90
        )

def test_generate_returns_response():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert result.text == "the answer"
        assert result.tokens == 99
        assert result.orchestration == "openai-compat"
        assert result.orchestration_version is None
        assert result.is_api_mode is True

def test_generate_forwards_headers():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(
            base_url="https://api.openai.com", headers={"Authorization": "Bearer token"}
        )
        transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        mock_post.assert_called_once()
        assert mock_post.call_args[1]["headers"] == {"Authorization": "Bearer token"}

def test_empty_choices_returns_empty_text():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [],
            "usage": {"completion_tokens": 0, "total_tokens": 0}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert result.text == ""
        assert result.tokens == 0

def test_satisfies_transport_protocol():
    transport = OpenAICompatTransport(base_url="https://api.openai.com")
    assert isinstance(transport, Transport)

def test_base_url_v1_suffix_stripped():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"completion_tokens": 1, "total_tokens": 2}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com/v1")
        transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        url = mock_post.call_args[0][0]
        assert url == "https://api.openai.com/v1/chat/completions"

def test_base_url_trailing_slash_stripped():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com/")
        transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        mock_post.assert_called_once_with(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-3.5",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.1
            },
            headers={},
            timeout=90
        )


# ---------------------------------------------------------------------------
# list_models() — model auto-discovery via GET /v1/models
# ---------------------------------------------------------------------------


def test_list_models_returns_ids():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "unsloth/Llama-3.1-8B-Instruct", "object": "model"},
                {"id": "phi3:3.8b", "object": "model"},
            ],
        }
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        models = transport.list_models()

        assert models == ["unsloth/Llama-3.1-8B-Instruct", "phi3:3.8b"]


def test_list_models_gets_v1_models_url():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "m1"}]}
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435/v1")
        transport.list_models()

        url = mock_get.call_args[0][0]
        assert url == "http://localhost:11435/v1/models"


def test_list_models_forwards_headers():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "m1"}]}
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(
            base_url="http://localhost:11435", headers={"Authorization": "Bearer token"}
        )
        transport.list_models()

        assert mock_get.call_args[1]["headers"] == {"Authorization": "Bearer token"}


def test_list_models_uses_short_timeout():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "m1"}]}
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        transport.list_models()

        # Metadata call — must not inherit generate()'s 90s.
        assert mock_get.call_args[1]["timeout"] == 15


def test_list_models_skips_non_dict_and_idless_elements():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": ["not-a-dict", {"object": "model"}, {"id": 123}, {"id": "good"}],
        }
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        assert transport.list_models() == ["good"]


def test_list_models_non_json_body_returns_empty():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("not json")
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        assert transport.list_models() == []


def test_list_models_non_dict_body_returns_empty():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = ["unexpected"]
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        assert transport.list_models() == []


def test_list_models_missing_data_returns_empty():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"object": "list"}
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        assert transport.list_models() == []


def test_list_models_raises_on_error_body():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "model service unavailable"}
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        with pytest.raises(TransportError):
            transport.list_models()


def test_list_models_skips_empty_and_whitespace_ids():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": "good"},
                {"id": ""},
                {"id": "   "},
                {"id": "also-good"},
            ]
        }
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        assert transport.list_models() == ["good", "also-good"]


def test_list_models_strips_surrounding_whitespace_from_ids():
    with patch("hermia.transport.openai_compat.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "  padded  "}]}
        mock_get.return_value = mock_response

        transport = OpenAICompatTransport(base_url="http://localhost:11435")
        assert transport.list_models() == ["padded"]
