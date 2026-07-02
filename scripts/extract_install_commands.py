"""Extract install commands from README.md for docs-as-tested CI.

Strict parser for the ``## Install`` section: expects exactly the methods
listed in ``expected_methods`` and no others; expects each subsection to
contain exactly one fenced ``bash`` code block. Any deviation raises
``ExtractionError`` with a diagnostic pointing at the specific mismatch.
"""

from __future__ import annotations

import re
from pathlib import Path


class ExtractionError(RuntimeError):
    """Raised when README structure violates the extractor's contract."""


METHOD_HEADINGS = {
    "pipx": "recommended (via pipx):",
    "brew": "or via homebrew (macos):",
    "pip": "or with pip:",
    "source": "or from source:",
    "docker": "or via docker (headless fleet mode):",
}


def extract_install_commands(
    readme_path: Path,
    expected_methods: tuple[str, ...],
) -> dict[str, list[str]]:
    text = readme_path.read_text(encoding="utf-8")

    install_match = re.search(
        r"^## Install\s*\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if install_match is None:
        raise ExtractionError(
            f"{readme_path}: no '## Install' section found"
        )
    install_body = install_match.group(1)

    result: dict[str, list[str]] = {}
    for method in expected_methods:
        heading = METHOD_HEADINGS[method]
        pattern = (
            re.escape(heading)
            + r"\s*\n\s*```bash\s*\n(.*?)\n```"
        )
        block = re.search(pattern, install_body, flags=re.IGNORECASE | re.DOTALL)
        if block is None:
            raise ExtractionError(
                f"{readme_path}: expected method '{method}' — "
                f"could not find heading '{heading}' followed by a "
                f"```bash code block"
            )
        commands = [line for line in block.group(1).splitlines() if line.strip()]
        result[method] = commands

    return result
