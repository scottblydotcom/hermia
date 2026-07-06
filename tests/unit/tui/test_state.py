"""
Tests for the hermia.tui.state module.
"""

from __future__ import annotations

from hermia.tui.state import FleetConfig, Host, HostSource, ModelChoice, ModelSource


def test_model_choice_defaults():
    mc = ModelChoice(name="test")
    assert mc.name == "test"
    assert mc.selected is False
    assert mc.size_bytes is None
    assert mc.quant is None
    assert mc.family is None
    assert mc.modality is None


def test_model_choice_selected_can_be_set():
    mc = ModelChoice(name="test", selected=True)
    assert mc.selected is True


def test_host_required_fields():
    h = Host(name="host1", url="http://example.com", engine="openai")
    assert h.name == "host1"
    assert h.url == "http://example.com"
    assert h.engine == "openai"
    assert h.auth_header_env is None
    assert h.hardware is None
    assert h.models == []


def test_host_optional_fields():
    mc = ModelChoice(name="model1")
    h = Host(
        name="host1",
        url="http://example.com",
        engine="openai",
        auth_header_env="API_KEY",
        hardware="gpu",
        models=[mc],
    )
    assert h.name == "host1"
    assert h.url == "http://example.com"
    assert h.engine == "openai"
    assert h.auth_header_env == "API_KEY"
    assert h.hardware == "gpu"
    assert h.models == [mc]


def test_fleet_config_defaults():
    fc = FleetConfig(name="fleet1")
    assert fc.name == "fleet1"
    assert fc.hosts == []
    assert fc.tests == []
    assert fc.repeat == 1


def test_fleet_config_full_construction():
    host = Host(name="host1", url="http://example.com", engine="openai")
    fc = FleetConfig(
        name="fleet1",
        hosts=[host],
        tests=["test1", "test2"],
        repeat=3,
    )
    assert fc.name == "fleet1"
    assert fc.hosts == [host]
    assert fc.tests == ["test1", "test2"]
    assert fc.repeat == 3


def test_host_source_is_protocol():
    assert hasattr(HostSource, "list_hosts")


def test_model_source_is_protocol():
    assert hasattr(ModelSource, "list_models")


async def fake_list_hosts() -> list[Host]:
    return []


def test_host_source_can_be_implemented():
    class FakeHostSource:
        async def list_hosts(self) -> list[Host]:
            return await fake_list_hosts()

    source: HostSource = FakeHostSource()  # Should not raise TypeError
    assert isinstance(source, HostSource)


async def fake_list_models(host: Host) -> list[ModelChoice]:
    return []


def test_model_source_can_be_implemented():
    class FakeModelSource:
        async def list_models(self, host: Host) -> list[ModelChoice]:
            return await fake_list_models(host)

    source: ModelSource = FakeModelSource()  # Should not raise TypeError
    assert isinstance(source, ModelSource)
