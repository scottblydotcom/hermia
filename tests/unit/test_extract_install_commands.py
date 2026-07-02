from pathlib import Path

from scripts.extract_install_commands import extract_install_commands

FIXTURES = Path(__file__).parent.parent / "fixtures" / "install_readmes"


def test_extract_pipx_from_minimal_readme():
    result = extract_install_commands(
        readme_path=FIXTURES / "minimal_pipx.md",
        expected_methods=("pipx",),
    )
    assert result == {"pipx": ["pipx install hermia"]}
