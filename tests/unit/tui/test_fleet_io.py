"""Tests for hermia.tui.fleet_io — YAML load/save for fleets and hosts.yaml."""
from pathlib import Path

import pytest
import yaml

from hermia.tui.fleet_io import (
    fleet_path,
    load_fleet,
    load_hosts_seed,
    save_fleet,
    save_hosts_seed,
)
from hermia.tui.state import FleetConfig, Host, ModelChoice


class TestFleetPath:
    def test_returns_fleets_subdir(self, tmp_path: Path) -> None:
        p = fleet_path("kwaainet-baseline", root=tmp_path)
        assert p == tmp_path / "fleets" / "kwaainet-baseline.yaml"


class TestSaveFleet:
    def test_creates_fleets_dir_if_missing(self, tmp_path: Path) -> None:
        config = FleetConfig(name="smoke")
        path = save_fleet(config, root=tmp_path)
        assert path.exists()
        assert path.parent.name == "fleets"

    def test_writes_minimal_yaml(self, tmp_path: Path) -> None:
        config = FleetConfig(name="smoke")
        path = save_fleet(config, root=tmp_path)
        data = yaml.safe_load(path.read_text())
        assert data["name"] == "smoke"
        assert data["tests"] == []
        assert data["hosts"] == []
        assert data["repeat"] == 1
        assert "created" in data
        assert "hermia_version" in data

    def test_writes_full_fleet(self, tmp_path: Path) -> None:
        config = FleetConfig(
            name="kwaainet-baseline",
            hosts=[
                Host(
                    name="eric-5090",
                    url="https://eric:11434",
                    engine="ollama",
                    hardware="RTX 5090",
                    auth_header_env="LITELLM_KEY",
                    models=[
                        ModelChoice(name="qwen3:32b", selected=True),
                        ModelChoice(name="qwen3-coder:30b", selected=True),
                        ModelChoice(name="llama3:70b", selected=False),
                    ],
                )
            ],
            tests=["prompt-injection-1", "jailbreak-1"],
            repeat=3,
        )
        path = save_fleet(config, root=tmp_path)
        data = yaml.safe_load(path.read_text())
        assert data["repeat"] == 3
        assert data["tests"] == ["prompt-injection-1", "jailbreak-1"]
        assert len(data["hosts"]) == 1
        h = data["hosts"][0]
        assert h["name"] == "eric-5090"
        assert h["url"] == "https://eric:11434"
        assert h["engine"] == "ollama"
        assert h["hardware"] == "RTX 5090"
        assert h["auth_header_env"] == "LITELLM_KEY"
        assert h["models"] == ["qwen3:32b", "qwen3-coder:30b"]

    def test_omits_optional_fields_when_none(self, tmp_path: Path) -> None:
        config = FleetConfig(
            name="minimal",
            hosts=[Host(name="h1", url="http://h1:11434", engine="ollama")],
        )
        path = save_fleet(config, root=tmp_path)
        data = yaml.safe_load(path.read_text())
        h = data["hosts"][0]
        assert "auth_header_env" not in h
        assert "hardware" not in h

    def test_never_writes_secret_value(self, tmp_path: Path) -> None:
        config = FleetConfig(
            name="secrets-test",
            hosts=[
                Host(
                    name="h1",
                    url="http://h1:11434",
                    engine="openai-compat",
                    auth_header_env="LITELLM_KEY",
                )
            ],
        )
        path = save_fleet(config, root=tmp_path)
        text = path.read_text()
        assert "LITELLM_KEY" in text
        assert "sk-" not in text
        assert "Bearer " not in text


class TestLoadFleet:
    def test_round_trip(self, tmp_path: Path) -> None:
        original = FleetConfig(
            name="rt",
            hosts=[
                Host(
                    name="h1",
                    url="http://h1:11434",
                    engine="ollama",
                    hardware="RTX 5090",
                    models=[ModelChoice(name="qwen3:32b", selected=True)],
                )
            ],
            tests=["prompt-injection-1"],
            repeat=2,
        )
        path = save_fleet(original, root=tmp_path)
        loaded = load_fleet(path)
        assert loaded.name == "rt"
        assert loaded.repeat == 2
        assert loaded.tests == ["prompt-injection-1"]
        assert len(loaded.hosts) == 1
        h = loaded.hosts[0]
        assert h.name == "h1"
        assert h.engine == "ollama"
        assert h.hardware == "RTX 5090"
        assert len(h.models) == 1
        assert h.models[0].name == "qwen3:32b"
        assert h.models[0].selected is True

    def test_load_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_fleet(tmp_path / "fleets" / "nope.yaml")

    def test_load_malformed_yaml_raises_yaml_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("name: smoke\n  this is: not valid yaml\n: : :")
        with pytest.raises(yaml.YAMLError):
            load_fleet(bad)

    def test_load_missing_required_name_raises_key_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "noname.yaml"
        bad.write_text("tests: []\nhosts: []\n")
        with pytest.raises(KeyError):
            load_fleet(bad)

    def test_load_handles_explicit_null_collections(self, tmp_path: Path) -> None:
        # PyYAML parses `tests:` (with no value) as None, not []. Without the
        # `or []` guard, list(None) and iteration would TypeError.
        path = tmp_path / "nulls.yaml"
        path.write_text("name: nulls\ntests:\nhosts:\nrepeat: 1\n")
        loaded = load_fleet(path)
        assert loaded.name == "nulls"
        assert loaded.tests == []
        assert loaded.hosts == []

    def test_load_handles_host_with_null_models_key(self, tmp_path: Path) -> None:
        # Same edge case at the host level — `models:` with no children.
        path = tmp_path / "nullmodels.yaml"
        path.write_text(
            "name: nm\n"
            "tests: []\n"
            "hosts:\n"
            "  - name: h1\n"
            "    url: http://h1\n"
            "    engine: ollama\n"
            "    models:\n"
        )
        loaded = load_fleet(path)
        assert loaded.hosts[0].models == []


class TestHostsSeed:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        seed_path = tmp_path / "hosts.yaml"
        hosts = [
            Host(
                name="eric-5090",
                url="https://eric:11434",
                engine="ollama",
                hardware="RTX 5090",
                auth_header_env="LITELLM_KEY",
            ),
            Host(name="m3-pro", url="https://m3:4000", engine="openai-compat"),
        ]
        save_hosts_seed(hosts, path=seed_path)
        assert seed_path.exists()

        loaded = load_hosts_seed(path=seed_path)
        assert len(loaded) == 2
        assert loaded[0].name == "eric-5090"
        assert loaded[0].hardware == "RTX 5090"
        assert loaded[0].auth_header_env == "LITELLM_KEY"
        assert loaded[1].name == "m3-pro"
        assert loaded[1].hardware is None

    def test_load_missing_seed_returns_empty_list(self, tmp_path: Path) -> None:
        loaded = load_hosts_seed(path=tmp_path / "nope.yaml")
        assert loaded == []

    def test_save_creates_parent_dir(self, tmp_path: Path) -> None:
        seed_path = tmp_path / ".config" / "hermia" / "hosts.yaml"
        save_hosts_seed([], path=seed_path)
        assert seed_path.exists()

    def test_seed_does_not_include_models(self, tmp_path: Path) -> None:
        seed_path = tmp_path / "hosts.yaml"
        hosts = [
            Host(
                name="h1",
                url="http://h1",
                engine="ollama",
                models=[ModelChoice(name="qwen3:32b", selected=True)],
            )
        ]
        save_hosts_seed(hosts, path=seed_path)
        text = seed_path.read_text()
        assert "qwen3:32b" not in text
        assert "models" not in text

    def test_load_seed_handles_explicit_null_hosts(self, tmp_path: Path) -> None:
        # `hosts:` with no children parses as None.
        seed_path = tmp_path / "nullhosts.yaml"
        seed_path.write_text("hosts:\n")
        assert load_hosts_seed(path=seed_path) == []
