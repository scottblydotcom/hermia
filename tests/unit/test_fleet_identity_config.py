"""The identity YAML block must survive load_fleet_config (ultra-review bug_001).

Regression for the ship-blocker where an `identity:` block was rejected as an
unrecognized key, making the whole SSH-identity feature unreachable via config.
Every prior identity test bypassed load_fleet_config with hand-built dicts.
"""
import pytest

from hermia.fleet import load_fleet_config
from hermia.identity import IdentityTransport, parse_identity_transport

_BASE = "fleet:\n  - name: n\n    host: http://h:11434\n"


def _load(tmp_path, yaml_text: str):
    f = tmp_path / "fleet.yaml"
    f.write_text(yaml_text)
    return load_fleet_config(f)


def test_valid_ssh_identity_block_loads_and_parses(tmp_path):
    entries = _load(tmp_path, _BASE + "    identity:\n      transport: ssh\n      ssh: gpu-node\n")
    assert parse_identity_transport(entries[0]) == IdentityTransport("ssh", "gpu-node")


def test_absent_identity_loads_as_api(tmp_path):
    entries = _load(tmp_path, _BASE)
    assert parse_identity_transport(entries[0]).kind == "api"


def test_unknown_identity_key_rejected_at_load(tmp_path):
    with pytest.raises(ValueError, match="unrecognized key"):
        _load(
            tmp_path,
            _BASE + "    identity:\n      transport: ssh\n      ssh: g\n      bogus: 1\n",
        )


def test_ssh_without_target_rejected_at_load(tmp_path):
    with pytest.raises(ValueError, match="ssh transport requires"):
        _load(tmp_path, _BASE + "    identity:\n      transport: ssh\n")


def test_reserved_wmi_transport_fails_fast_at_load(tmp_path):
    with pytest.raises(NotImplementedError, match="wmi"):
        _load(tmp_path, _BASE + "    identity:\n      transport: wmi\n")


def test_arg_injection_target_rejected_at_load(tmp_path):
    with pytest.raises(ValueError, match="arg-injection"):
        _load(
            tmp_path,
            _BASE + "    identity:\n      transport: ssh\n      ssh: '-oProxyCommand=x'\n",
        )
