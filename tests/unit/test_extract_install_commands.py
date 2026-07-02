from pathlib import Path

from scripts.extract_install_commands import extract_install_commands

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
