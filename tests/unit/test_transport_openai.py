import pytest
from unittest.mock import patch, MagicMock
from hermia.transport.base import Response, Transport
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

        transport = OpenAICompatTransport(base_url="https://api.openai.com", headers={"Authorization": "Bearer token"})
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
