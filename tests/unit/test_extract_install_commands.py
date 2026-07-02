import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.extract_install_commands import ExtractionError, extract_install_commands

FIXTURES = Path(__file__).parent.parent / "fixtures" / "install_readmes"


def test_extract_pipx_from_minimal_readme():
    result = extract_install_commands(
        readme_path=FIXTURES / "minimal_pipx.md",
        expected_methods=("pipx",),
    )
    assert result == {"pipx": ["pipx install hermia"]}


def test_extract_source_install_preserves_command_order():
    result = extract_install_commands(
        readme_path=FIXTURES / "source_install.md",
        expected_methods=("source",),
    )
    assert result == {
        "source": [
            "git clone https://github.com/scottblydotcom/hermia",
            "cd hermia",
            "pip install -e .",
        ]
    }


def test_extract_all_five_methods_from_full_readme():
    result = extract_install_commands(
        readme_path=FIXTURES / "full_readme.md",
        expected_methods=("pipx", "brew", "pip", "source", "docker"),
    )

    assert result["pipx"] == ["pipx install hermia"]
    assert result["brew"] == ["brew install scottblydotcom/tap/hermia"]
    assert result["pip"] == ["pip install hermia"]
    assert result["source"] == [
        "git clone https://github.com/scottblydotcom/hermia",
        "cd hermia",
        "pip install -e .",
    ]
    assert result["docker"][0] == "mkdir -p results && chmod 777 results"
    assert result["docker"][1].startswith("docker run --rm --network host")
    assert result["docker"][-1].strip() == "--fleet fleets/local.yaml"
    assert len(result["docker"]) >= 2


def test_missing_install_section_raises():
    with pytest.raises(ExtractionError, match="no '## Install' section found"):
        extract_install_commands(
            readme_path=FIXTURES / "missing_install_section.md",
            expected_methods=("pipx",),
        )


def test_missing_expected_method_heading_raises():
    with pytest.raises(ExtractionError, match="expected method 'pipx'"):
        extract_install_commands(
            readme_path=FIXTURES / "missing_pipx_heading.md",
            expected_methods=("pipx",),
        )


def test_expected_method_without_bash_code_block_raises():
    with pytest.raises(ExtractionError, match="expected method 'pipx'"):
        extract_install_commands(
            readme_path=FIXTURES / "pipx_no_code_fence.md",
            expected_methods=("pipx",),
        )


def test_cli_emits_json_for_one_method(tmp_path):
    fixture = FIXTURES / "full_readme.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.extract_install_commands",
            "--readme",
            str(fixture),
            "--method",
            "pipx",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload == ["pipx install hermia"]


def test_cli_exits_nonzero_on_extraction_error():
    fixture = FIXTURES / "missing_install_section.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.extract_install_commands",
            "--readme",
            str(fixture),
            "--method",
            "pipx",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "no '## Install' section found" in result.stderr
