from unittest.mock import patch

from hermia.transport.base import Transport
from hermia.transport.ollama import OllamaTransport


def test_generate_posts_to_api_chat():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "the answer"},
            "eval_count": 42,
            "done": True,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        transport.generate("test-model", [{"role": "user", "content": "hello"}])

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "/api/chat" in args[0]
        assert kwargs["json"] == {
            "model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
            "options": {"temperature": 0.1},
        }


def test_generate_returns_response():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "the answer"},
            "eval_count": 42,
            "done": True,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        response = transport.generate("test-model", [{"role": "user", "content": "hello"}])

        assert response.text == "the answer"
        assert response.tokens == 42
        assert response.elapsed_sec is not None
        assert response.orchestration == "ollama"
        assert response.orchestration_version == "0.24.0"
        assert response.is_api_mode is False


def test_generate_sends_custom_headers():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "the answer"},
            "eval_count": 42,
            "done": True,
        }
        headers = {"Authorization": "Bearer token"}
        transport = OllamaTransport(base_url="http://localhost:11434", headers=headers)
        transport.generate("test-model", [{"role": "user", "content": "hello"}])

        mock_post.assert_called_once()
        assert mock_post.call_args[1]["headers"] == headers


def test_version_fetch_failure_returns_none():
    with patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("Connection failed")
        transport = OllamaTransport(base_url="http://localhost:11434")
        assert transport._fetch_version() is None


def test_satisfies_transport_protocol():
    with patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        transport = OllamaTransport(base_url="http://localhost:11434")
        assert isinstance(transport, Transport)


def test_base_url_trailing_slash_stripped():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "the answer"},
            "eval_count": 42,
            "done": True,
        }
        transport = OllamaTransport(base_url="http://localhost:11434/")
        transport.generate("test-model", [{"role": "user", "content": "hello"}])

        mock_post.assert_called_once()
        args, _ = mock_post.call_args
        assert args[0] == "http://localhost:11434/api/chat"


def test_generate_forwards_seed_to_options():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "ok"},
            "eval_count": 1,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        transport.generate("m", [{"role": "user", "content": "hi"}], seed=42)
        options = mock_post.call_args[1]["json"]["options"]
        assert options["seed"] == 42


def test_generate_forwards_top_p_top_k_repeat_penalty():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "ok"},
            "eval_count": 1,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        transport.generate(
            "m", [{"role": "user", "content": "hi"}],
            top_p=0.9, top_k=40, repeat_penalty=1.1,
        )
        options = mock_post.call_args[1]["json"]["options"]
        assert options["top_p"] == 0.9
        assert options["top_k"] == 40
        assert options["repeat_penalty"] == 1.1


def test_generate_omits_absent_sampling_keys():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "ok"},
            "eval_count": 1,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        transport.generate("m", [{"role": "user", "content": "hi"}], temperature=0.0)
        options = mock_post.call_args[1]["json"]["options"]
        assert set(options.keys()) == {"temperature"}


def test_generate_num_predict_num_ctx_forwarded():
    with patch("hermia.transport.ollama.requests.post") as mock_post, \
         patch("hermia.transport.ollama.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"version": "0.24.0"}
        mock_post.return_value.json.return_value = {
            "message": {"role": "assistant", "content": "ok"},
            "eval_count": 1,
        }
        transport = OllamaTransport(base_url="http://localhost:11434")
        transport.generate(
            "m", [{"role": "user", "content": "hi"}],
            num_predict=512, num_ctx=4096,
        )
        options = mock_post.call_args[1]["json"]["options"]
        assert options["num_predict"] == 512
        assert options["num_ctx"] == 4096
