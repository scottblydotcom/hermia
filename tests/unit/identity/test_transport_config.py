"""Tests for the per-host identity transport selector (hermia-cfqv wiring)."""
import pytest

from hermia.identity.transport_config import IdentityTransport, parse_identity_transport


def test_absent_block_defaults_to_api_null():
    result = parse_identity_transport({"name": "a", "host": "http://h:11434"})
    assert result == IdentityTransport("api", None)


def test_explicit_api():
    t = parse_identity_transport({"identity": {"transport": "api"}})
    assert t.kind == "api" and t.ssh_target is None


def test_ssh_requires_target():
    result = parse_identity_transport({"identity": {"transport": "ssh", "ssh": "rampagev"}})
    assert result == IdentityTransport("ssh", "rampagev")


def test_ssh_without_target_is_error():
    with pytest.raises(ValueError, match="ssh.*target"):
        parse_identity_transport({"identity": {"transport": "ssh"}})


def test_wmi_and_agent_are_not_yet_implemented():
    for kind in ("wmi", "agent"):
        with pytest.raises(NotImplementedError, match=kind):
            parse_identity_transport({"identity": {"transport": kind}})


def test_unknown_transport_is_error():
    with pytest.raises(ValueError, match="unknown identity transport"):
        parse_identity_transport({"identity": {"transport": "telepathy"}})


def test_ssh_target_starting_with_dash_is_rejected():
    # Arg-injection guard: a target like "-oProxyCommand=..." must not be accepted.
    with pytest.raises(ValueError, match="arg-injection"):
        parse_identity_transport(
            {"identity": {"transport": "ssh", "ssh": "-oProxyCommand=touch /tmp/x"}}
        )
