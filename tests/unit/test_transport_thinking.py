"""hermia-cv5z: transports capture the reasoning 'thinking' channel.

Ollama returns chain-of-thought in message['thinking']; OpenAI-compatible
backends return it in message['reasoning_content'] (or 'reasoning'). Both were
being discarded. These tests pin that the channel now lands on Response.thinking
while Response.text still comes from message['content'] (grading is unchanged).
"""
from unittest.mock import MagicMock, patch

from hermia.transport.base import Response
from hermia.transport.ollama import OllamaTransport
from hermia.transport.openai_compat import OpenAICompatTransport

# ── Response dataclass ─────────────────────────────────────────────────────────

def test_response_thinking_defaults_empty() -> None:
    """Backward-compat: constructing a Response without thinking yields ""."""
    response = Response(
        text="t",
        tokens=1,
        elapsed_sec=0.0,
        orchestration="o",
        orchestration_version=None,
        is_api_mode=False,
    )
    assert response.thinking == ""


# ── Ollama transport ───────────────────────────────────────────────────────────

def test_ollama_captures_thinking_field() -> None:
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "4",
                "thinking": "the user asks 2+2, that is 4",
            },
            "eval_count": 10,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        response = transport.generate("m", [{"role": "user", "content": "What is 2+2?"}])

        assert response.text == "4"
        assert response.thinking == "the user asks 2+2, that is 4"


def test_ollama_thinking_defaults_empty_when_absent() -> None:
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "4"},
            "eval_count": 10,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        response = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert response.text == "4"
        assert response.thinking == ""


# ── OpenAI-compatible transport ────────────────────────────────────────────────

def _openai_post(payload: dict) -> MagicMock:
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    return mock_response


def test_openai_captures_reasoning_content() -> None:
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value = _openai_post({
            "choices": [{"message": {
                "role": "assistant",
                "content": "the answer",
                "reasoning_content": "step by step because ...",
            }}],
            "usage": {"completion_tokens": 5},
        })
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert result.text == "the answer"
        assert result.thinking == "step by step because ..."


def test_openai_reasoning_fallback_key() -> None:
    """Some backends use 'reasoning' rather than 'reasoning_content'."""
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value = _openai_post({
            "choices": [{"message": {
                "role": "assistant",
                "content": "the answer",
                "reasoning": "fallback trace",
            }}],
            "usage": {"completion_tokens": 5},
        })
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert result.thinking == "fallback trace"


def test_openai_thinking_defaults_empty_when_absent() -> None:
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value = _openai_post({
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 5},
        })
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert result.text == "the answer"
        assert result.thinking == ""


def test_ollama_nonstring_thinking_coerced_to_empty() -> None:
    """A non-string thinking field (e.g. a list from a gateway) must not poison
    Response.thinking — the runner .strip()s it downstream (hermia-cv5z)."""
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "4",
                "thinking": ["step one", "step two"],
            },
            "eval_count": 10,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        response = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert response.text == "4"
        assert response.thinking == ""
        assert isinstance(response.thinking, str)


def test_openai_nonstring_reasoning_coerced_to_empty() -> None:
    """Some backends return reasoning as a list/dict of blocks; it must not reach
    Response.thinking as a non-string (hermia-cv5z)."""
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value = _openai_post({
            "choices": [{"message": {
                "role": "assistant",
                "content": "the answer",
                "reasoning": [{"type": "thinking", "text": "block"}],
            }}],
            "usage": {"completion_tokens": 5},
        })
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert result.text == "the answer"
        assert result.thinking == ""
        assert isinstance(result.thinking, str)


def test_openai_prefers_string_reasoning_over_nonstring_reasoning_content() -> None:
    """When reasoning_content is a non-string (structured blocks) but 'reasoning'
    holds the plain-text trace, capture the string rather than blanking it
    (hermia-cv5z)."""
    with patch("hermia.transport.openai_compat.requests.post") as mock_post:
        mock_post.return_value = _openai_post({
            "choices": [{"message": {
                "role": "assistant",
                "content": "the answer",
                "reasoning_content": [{"type": "thinking", "text": "block"}],
                "reasoning": "plain text trace",
            }}],
            "usage": {"completion_tokens": 5},
        })
        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("m", [{"role": "user", "content": "hi"}])

        assert result.thinking == "plain text trace"
