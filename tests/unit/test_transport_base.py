import pytest
from hermia.transport.base import Response, Transport


def test_response_fields():
    response = Response(
        text="test text",
        tokens=100,
        elapsed_sec=0.5,
        orchestration="test_orchestration",
        orchestration_version="1.0.0",
        is_api_mode=True,
    )
    assert response.text == "test text"
    assert response.tokens == 100
    assert response.elapsed_sec == 0.5
    assert response.orchestration == "test_orchestration"
    assert response.orchestration_version == "1.0.0"
    assert response.is_api_mode is True


def test_response_is_frozen():
    response = Response(
        text="test text",
        tokens=100,
        elapsed_sec=0.5,
        orchestration="test_orchestration",
        orchestration_version="1.0.0",
        is_api_mode=True,
    )
    with pytest.raises(AttributeError):
        response.text = "new text"  # type: ignore[misc]


def test_response_version_can_be_none():
    response = Response(
        text="test text",
        tokens=100,
        elapsed_sec=0.5,
        orchestration="test_orchestration",
        orchestration_version=None,
        is_api_mode=True,
    )
    assert response.orchestration_version is None


def test_transport_protocol_structural():
    class MockTransport:
        def generate(self, model: str, messages: list[dict[str, str]], **opts: object) -> Response:
            return Response(
                text="test",
                tokens=0,
                elapsed_sec=0.0,
                orchestration="test",
                orchestration_version=None,
                is_api_mode=False,
            )

    assert isinstance(MockTransport(), Transport)


def test_transport_protocol_rejects_missing_generate():
    class MockTransport:
        def other_method(self) -> None:
            pass

    assert not isinstance(MockTransport(), Transport)
