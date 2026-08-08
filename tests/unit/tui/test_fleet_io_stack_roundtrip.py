"""Fleet YAML `stack:` block survives into Host (hermia-0hqm).

fleet_io previously dropped `stack:` on load ("no Host field"), so a TUI run
could not resolve backend_stack — the field the corpus uses for version-confound
analysis. These tests cover both layouts fleet_io accepts: the headless runner's
`fleet:` key and the TUI's own `hosts:` key.
"""
from pathlib import Path

import yaml

from hermia.tui.fleet_io import load_fleet, save_fleet
from hermia.tui.state import FleetConfig, Host, ModelChoice

STACK = {"gpu_arch": "sm_89", "runtime_version": "cuda-12.4"}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "fleet.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


class TestHeadlessFormat:
    def test_load_preserves_stack_block(self, tmp_path: Path) -> None:
        path = _write(tmp_path, {
            "fleet": [{
                "name": "h1",
                "host": "http://x:11434",
                "stack": dict(STACK),
            }],
        })
        config = load_fleet(path)
        assert config.hosts[0].stack == STACK

    def test_host_without_stack_loads_as_none(self, tmp_path: Path) -> None:
        path = _write(tmp_path, {
            "fleet": [{"name": "h1", "host": "http://x:11434"}],
        })
        assert load_fleet(path).hosts[0].stack is None

    def test_non_dict_stack_is_ignored_rather_than_crashing(self, tmp_path: Path) -> None:
        """A malformed config still loads — same stance as the rest of fleet_io."""
        path = _write(tmp_path, {
            "fleet": [{"name": "h1", "host": "http://x:11434", "stack": "sm_89"}],
        })
        assert load_fleet(path).hosts[0].stack is None


class TestTuiFormat:
    def test_load_preserves_stack_block(self, tmp_path: Path) -> None:
        path = _write(tmp_path, {
            "name": "f1",
            "hosts": [{
                "name": "h1",
                "url": "http://x:11434",
                "engine": "ollama",
                "stack": dict(STACK),
            }],
        })
        assert load_fleet(path).hosts[0].stack == STACK

    def test_host_without_stack_loads_as_none(self, tmp_path: Path) -> None:
        path = _write(tmp_path, {
            "name": "f1",
            "hosts": [{"name": "h1", "url": "http://x:11434", "engine": "ollama"}],
        })
        assert load_fleet(path).hosts[0].stack is None


class TestRoundTrip:
    def test_stack_survives_save_then_load(self, tmp_path: Path) -> None:
        config = FleetConfig(
            name="f1",
            tests=["t1"],
            hosts=[Host(
                name="h1",
                url="http://x:11434",
                engine="ollama",
                stack=dict(STACK),
                models=[ModelChoice(name="m1", selected=True)],
            )],
        )
        path = save_fleet(config, root=tmp_path)
        assert load_fleet(path).hosts[0].stack == STACK

    def test_stack_key_is_omitted_when_absent(self, tmp_path: Path) -> None:
        """Do not emit `stack: null` — keep saved YAML clean, as with hardware."""
        config = FleetConfig(
            name="f1",
            tests=["t1"],
            hosts=[Host(name="h1", url="http://x:11434", engine="ollama")],
        )
        path = save_fleet(config, root=tmp_path)
        saved = yaml.safe_load(path.read_text())
        assert "stack" not in saved["hosts"][0]
