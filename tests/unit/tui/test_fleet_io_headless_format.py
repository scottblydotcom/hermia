"""The TUI must load headless (CLI) fleet YAML, not silently return zero hosts.

hermia-79z6. `load_fleet` read only the TUI's own `hosts:` key, while every
headless config uses `fleet:`. Because the guard was `raw.get("hosts") or []`,
opening a real fleet in the TUI produced a config with NO hosts and NO error —
23 of the 25 committed configs were affected.

The conversion already existed in the other direction: `fleet._tui_fleet_to_entries`
lets the headless runner read TUI files. These tests pin the reverse mapping so
the two formats are interchangeable both ways.
"""
import textwrap
from pathlib import Path

import pytest

from hermia.runner import load_tests_all
from hermia.tui.fleet_io import load_fleet


def _write(tmp_path: Path, body: str, name: str = "f.yaml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body))
    return p


# ── Headless (CLI) format is accepted ────────────────────────────────────────


class TestHeadlessFormatLoads:
    def test_fleet_key_produces_hosts(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: smoke
            fleet:
              - name: bh-m3-36gb
                host: http://192.168.2.2:11434
                models:
                  - mistral:7b
              - name: bh-m1-16gb
                host: http://192.168.2.4:11434
                models:
                  - mistral:7b
        """)
        cfg = load_fleet(p)
        assert [h.name for h in cfg.hosts] == ["bh-m3-36gb", "bh-m1-16gb"]

    def test_host_key_maps_to_url(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://10.0.0.1:11434'}
        """)
        assert load_fleet(p).hosts[0].url == "http://10.0.0.1:11434"

    def test_transport_maps_to_engine(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'https://x/v1', transport: openai-compat}
        """)
        assert load_fleet(p).hosts[0].engine == "openai-compat"

    def test_missing_transport_defaults_to_ollama(self, tmp_path: Path) -> None:
        # Mirrors fleet._tui_fleet_to_entries, which defaults engine -> ollama.
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://h:11434'}
        """)
        assert load_fleet(p).hosts[0].engine == "ollama"

    def test_auth_bearer_key_env_maps_to_auth_header_env(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - name: a
                host: 'https://x/v1'
                auth:
                  bearer:
                    key_env: MY_TOKEN
        """)
        assert load_fleet(p).hosts[0].auth_header_env == "MY_TOKEN"

    def test_models_become_selected_choices(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://h:11434', models: [mistral:7b, qwen3:8b]}
        """)
        models = load_fleet(p).hosts[0].models
        assert [m.name for m in models] == ["mistral:7b", "qwen3:8b"]
        assert all(m.selected for m in models), "loaded models must be runnable"

    def test_models_auto_yields_no_preselection(self, tmp_path: Path) -> None:
        # 'auto' is a headless directive meaning "discover on the host". The TUI
        # has a picker for that; it must not crash or invent a model named auto.
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://h:11434', models: auto}
        """)
        assert load_fleet(p).hosts[0].models == []

    def test_absent_models_yields_empty_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://h:11434'}
        """)
        assert load_fleet(p).hosts[0].models == []

    def test_test_timeout_is_ignored_not_fatal(self, tmp_path: Path) -> None:
        # test_timeout has no Host field; it must not break the load.
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://h:11434', test_timeout: 300}
        """)
        assert load_fleet(p).hosts[0].name == "a"


# ── tests: key semantics ─────────────────────────────────────────────────────


class TestTestsKeyDefaulting:
    def test_absent_tests_key_defaults_to_the_full_corpus(self, tmp_path: Path) -> None:
        # Headless configs omit `tests:` because the CLI always runs the whole
        # corpus. Loading one into the TUI with zero tests would be a second
        # silent-empty path: hosts present, but no trials.
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a, host: 'http://h:11434', models: [m:7b]}
        """)
        cfg = load_fleet(p)
        assert len(cfg.tests) == len(load_tests_all())
        assert cfg.tests, "a headless config must not load as zero trials"

    def test_present_tests_key_is_honoured_exactly(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            tests: [tool-calling-basic]
            fleet:
              - {name: a, host: 'http://h:11434'}
        """)
        assert load_fleet(p).tests == ["tool-calling-basic"]

    def test_explicit_empty_tests_stays_empty(self, tmp_path: Path) -> None:
        # A TUI-saved fleet always writes the key. `tests: []` means the user
        # deselected everything — do NOT silently run all 30 instead.
        p = _write(tmp_path, """
            name: s
            tests: []
            hosts:
              - {name: a, url: 'http://h:11434', engine: ollama}
        """)
        assert load_fleet(p).tests == []


# ── The silent-empty failure is now loud ─────────────────────────────────────


class TestNameDerivation:
    def test_headless_config_without_a_name_uses_the_filename(self, tmp_path: Path) -> None:
        # Headless configs have no `name:` — the CLI never needed one. Without a
        # fallback the TUI refuses to open 8 of the committed configs; worse, an
        # empty name makes RunnerScreen skip results_dir entirely, so the run
        # would discard every row silently.
        p = _write(tmp_path, """
            fleet:
              - {name: a, host: 'http://h:11434'}
        """, name="fleet-2026-08-05-mobile-lab-smoke.yaml")
        assert load_fleet(p).name == "fleet-2026-08-05-mobile-lab-smoke"

    def test_headless_name_when_present_wins_over_the_filename(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: declared-name
            fleet:
              - {name: a, host: 'http://h:11434'}
        """, name="ignored.yaml")
        assert load_fleet(p).name == "declared-name"

    def test_derived_name_is_never_empty(self, tmp_path: Path) -> None:
        # A falsy name reaching FleetConfig is the bug this guards: save_fleet
        # would write fleets/None.yaml and the runner would drop the rows.
        p = _write(tmp_path, """
            fleet:
              - {name: a, host: 'http://h:11434'}
        """, name="x.yaml")
        assert load_fleet(p).name


class TestNoSilentEmpty:
    def test_neither_hosts_nor_fleet_key_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            repeat: 1
        """)
        with pytest.raises(KeyError) as exc:
            load_fleet(p)
        assert "hosts" in str(exc.value) or "fleet" in str(exc.value)

    def test_explicit_empty_hosts_list_is_still_allowed(self, tmp_path: Path) -> None:
        # A part-built fleet saved from the TUI is legitimate — only a config
        # with NO host key at all is malformed.
        p = _write(tmp_path, """
            name: s
            tests: []
            hosts: []
        """)
        assert load_fleet(p).hosts == []

    def test_fleet_entry_missing_host_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - {name: a}
        """)
        with pytest.raises(KeyError):
            load_fleet(p)

    def test_fleet_entry_missing_name_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet:
              - {host: 'http://h:11434'}
        """)
        with pytest.raises(KeyError):
            load_fleet(p)

    def test_fleet_must_be_a_list(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            fleet: nonsense
        """)
        with pytest.raises((TypeError, ValueError)):
            load_fleet(p)


# ── TUI format is unchanged ──────────────────────────────────────────────────


class TestTuiFormatRegression:
    def test_hosts_key_still_loads(self, tmp_path: Path) -> None:
        p = _write(tmp_path, """
            name: s
            tests: [tool-calling-basic]
            repeat: 2
            hosts:
              - name: a
                url: 'http://h:11434'
                engine: ollama
                auth_header_env: TOK
                hardware: metal
                models: [mistral:7b]
        """)
        cfg = load_fleet(p)
        h = cfg.hosts[0]
        assert (h.name, h.url, h.engine) == ("a", "http://h:11434", "ollama")
        assert h.auth_header_env == "TOK"
        assert h.hardware == "metal"
        assert [m.name for m in h.models] == ["mistral:7b"]
        assert cfg.repeat == 2

    def test_hosts_key_wins_when_both_present(self, tmp_path: Path) -> None:
        # Matches the headless loader, which prefers `fleet:` when both exist by
        # only converting TUI format if "fleet" is absent. Here the TUI's own
        # key is the native one, so it takes precedence — but the behaviour must
        # be defined rather than accidental.
        p = _write(tmp_path, """
            name: s
            hosts:
              - {name: from-hosts, url: 'http://h:11434', engine: ollama}
            fleet:
              - {name: from-fleet, host: 'http://h:11434'}
        """)
        assert [h.name for h in load_fleet(p).hosts] == ["from-hosts"]


# ── The actual reported failure, on the real committed configs ───────────────


class TestRealConfigs:
    def test_the_reported_config_loads_three_hosts(self) -> None:
        # fleets/ is gitignored, so skip when the real files are absent (CI).
        p = Path("fleets/fleet-2026-08-05-mobile-lab-smoke.yaml")
        if not p.exists():
            pytest.skip("local fleets/ not present")
        cfg = load_fleet(p)
        assert len(cfg.hosts) == 3, "this is the config that loaded as zero hosts"
        assert all(h.url.startswith("http://") for h in cfg.hosts)
        assert cfg.tests, "must not load as zero trials"
