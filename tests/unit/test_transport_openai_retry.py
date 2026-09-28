from unittest.mock import MagicMock, patch

import pytest
import requests

from hermia.transport.base import TransportError
from hermia.transport.openai_compat import OpenAICompatTransport


def test_generate_retries_5xx_up_to_2_additional_times():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post, \
         patch("hermia.transport.openai_compat.time.sleep") as mock_sleep:
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 500
        mock_response_1.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 503
        mock_response_2.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "503 Service Unavailable"
        )
        mock_response_3 = MagicMock()
        mock_response_3.status_code = 200
        mock_response_3.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.side_effect = [mock_response_1, mock_response_2, mock_response_3]

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert result.text == "the answer"
        assert result.retries == 2
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0].args == (0.5,)
        assert mock_sleep.call_args_list[1].args == (2.0,)


def test_generate_elapsed_sec_excludes_retry_backoff_time():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post, \
         patch("hermia.transport.openai_compat.time.sleep") as mock_sleep, \
         patch("hermia.transport.openai_compat.time.monotonic") as mock_monotonic:
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 500
        mock_response_1.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.side_effect = [mock_response_1, mock_response_2]
        # t0 resets each attempt: attempt 1 sets t0=0 (its duration is never
        # measured since it fails and retries). Attempt 2 sets t0=100, then
        # succeeds at t=101 (a fast 1s call). elapsed_sec must be 1.0, not
        # 101.0 (which would include the failed attempt + backoff gap).
        mock_monotonic.side_effect = [0, 100, 101]

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert result.elapsed_sec == 1.0
        assert mock_sleep.call_count == 1


def test_generate_raises_immediately_on_4xx():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post, \
         patch("hermia.transport.openai_compat.time.sleep") as mock_sleep:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        with pytest.raises(requests.exceptions.HTTPError):
            transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert mock_post.call_count == 1
        assert mock_sleep.call_count == 0


def test_generate_raises_transport_error_on_exhausted_retries():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post, \
         patch("hermia.transport.openai_compat.time.sleep") as mock_sleep:
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 500
        mock_response_1.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 502
        mock_response_2.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "502 Bad Gateway"
        )
        mock_response_3 = MagicMock()
        mock_response_3.status_code = 503
        mock_response_3.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "503 Service Unavailable"
        )
        mock_post.side_effect = [mock_response_1, mock_response_2, mock_response_3]

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        with pytest.raises(TransportError) as exc_info:
            transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert exc_info.value.kind == "openai-compat-retry-exhausted"
        assert "3 attempts" in str(exc_info.value)
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0].args == (0.5,)
        assert mock_sleep.call_args_list[1].args == (2.0,)


def test_generate_no_retries_on_first_success():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post, \
         patch("hermia.transport.openai_compat.time.sleep") as mock_sleep:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "the answer"}}],
            "usage": {"completion_tokens": 99, "total_tokens": 120}
        }
        mock_post.return_value = mock_response

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        result = transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert result.text == "the answer"
        assert result.retries == 0
        assert mock_post.call_count == 1
        assert mock_sleep.call_count == 0


def test_generate_raises_transport_error_on_body_error_even_after_retries():
    with patch("hermia.transport.openai_compat.requests.post") as mock_post, \
         patch("hermia.transport.openai_compat.time.sleep") as mock_sleep:
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 500
        mock_response_1.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "error": {"message": "Invalid request", "type": "invalid_request_error"}
        }
        mock_post.side_effect = [mock_response_1, mock_response_2]

        transport = OpenAICompatTransport(base_url="https://api.openai.com")
        with pytest.raises(TransportError) as exc_info:
            transport.generate("gpt-3.5", [{"role": "user", "content": "Hello"}])

        assert "invalid_request_error" in str(exc_info.value)
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args_list[0].args == (0.5,)
