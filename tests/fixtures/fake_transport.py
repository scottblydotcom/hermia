"""FakeTransport — single shared fixture for probe and runner tests.

Scripts deterministic mixes of pass/refuse/fail/error responses without
ever touching a real host. Used by every test that drives probe.py or the
fleet runner without a live network.

Keys for responses / errors:
    "<test_id>:<model_name>"  — exact match
    "<test_id>"               — any model on that test
    "<model_name>"            — any test on that model
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class FakeTransport:
    models: list[str] = field(default_factory=list)
    responses: dict[str, str] = field(default_factory=dict)
    errors: dict[str, Exception] = field(default_factory=dict)
    default_response: str = ""
    fail_with: Exception | None = None
    delay_seconds: float = 0.0

    async def list_models(self) -> list[str]:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.fail_with is not None:
            raise self.fail_with
        return list(self.models)

    async def send(self, *, model: str, test: str, prompt: str) -> str:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        key_full = f"{test}:{model}"
        if key_full in self.errors:
            raise self.errors[key_full]
        if test in self.errors:
            raise self.errors[test]
        if model in self.errors:
            raise self.errors[model]
        if key_full in self.responses:
            return self.responses[key_full]
        if test in self.responses:
            return self.responses[test]
        if model in self.responses:
            return self.responses[model]
        return self.default_response
