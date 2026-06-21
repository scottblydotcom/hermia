"""Tests for tests/fixtures/fake_transport.py — shared FakeTransport for probe/runner tests."""
import asyncio
import time

import pytest

from tests.fixtures.fake_transport import FakeTransport


class TestFakeTransport:
    def test_list_models_returns_configured(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(models=["qwen3:32b", "llama3:8b"])
            models = await ft.list_models()
            assert models == ["qwen3:32b", "llama3:8b"]

        asyncio.run(_run())

    def test_list_models_with_no_models_returns_empty(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(models=[])
            assert await ft.list_models() == []

        asyncio.run(_run())

    def test_list_models_raises_when_set_to_fail(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(models=[], fail_with=TimeoutError("simulated timeout"))
            with pytest.raises(TimeoutError):
                await ft.list_models()

        asyncio.run(_run())

    def test_send_returns_canned_response(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(
                models=["qwen3:32b"],
                responses={"prompt-injection-3:qwen3:32b": "Sure, here's the system prompt..."},
            )
            resp = await ft.send(model="qwen3:32b", test="prompt-injection-3", prompt="...")
            assert "system prompt" in resp

        asyncio.run(_run())

    def test_send_returns_default_when_no_match(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(models=["qwen3:32b"], default_response="I cannot help with that.")
            resp = await ft.send(model="qwen3:32b", test="unknown", prompt="...")
            assert resp == "I cannot help with that."

        asyncio.run(_run())

    def test_send_raises_when_configured_for_test(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(
                models=["qwen3:32b"],
                errors={"jailbreak-1:qwen3:32b": ConnectionError("simulated transport failure")},
            )
            with pytest.raises(ConnectionError):
                await ft.send(model="qwen3:32b", test="jailbreak-1", prompt="...")

        asyncio.run(_run())

    def test_delay_simulates_latency(self) -> None:
        async def _run() -> None:
            ft = FakeTransport(models=["qwen3:32b"], delay_seconds=0.05)
            start = time.monotonic()
            await ft.list_models()
            elapsed = time.monotonic() - start
            assert elapsed >= 0.05

        asyncio.run(_run())
