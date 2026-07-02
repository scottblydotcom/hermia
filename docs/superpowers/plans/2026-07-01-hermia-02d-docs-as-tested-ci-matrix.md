# hermia-02d — Docs-as-tested CI matrix implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub Actions workflow that extracts the five install commands from README.md's `## Install` section and runs them literally in a matrix of clean environments (macOS + Linux, Python 3.11/3.12/3.13 where applicable), so any README drift that breaks an install path fails CI.

**Architecture:** A strict Python script (`scripts/extract_install_commands.py`) parses `README.md` and emits per-method JSON. A new workflow (`.github/workflows/docs-as-tested.yml`) runs the script and dispatches a matrix of 20 install jobs. Each job runs the extracted commands verbatim (except the docker leg, which pulls the image and asserts `hermia --version` inside it — see spec §Docker leg — a documented deviation from literal execution).

**Tech Stack:** Python 3.11+ (extractor + tests), pytest (extractor tests), GitHub Actions (workflow), Homebrew tap `scottblydotcom/tap`, ghcr.io image `scottblydotcom/hermia`.

**Spec:** `docs/superpowers/specs/2026-07-01-hermia-02d-docs-as-tested-ci-matrix-design.md`

**Bead:** hermia-02d (P1, blocks hermia-4e8 = v0.2.0 cut)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/extract_install_commands.py` (new) | Parse README.md and emit install commands per method, in strict mode |
| `tests/unit/test_extract_install_commands.py` (new) | Unit tests for the extractor: happy path per method, strict-mode failures |
| `tests/fixtures/install_readmes/` (new dir) | Fixture README files driving the extractor's tests |
| `.github/workflows/docs-as-tested.yml` (new) | Matrix workflow — 20 jobs across 5 install methods × supported (OS, Python) combos |
| `README.md` (modified, line 145) | Fix `scottbly/tap` → `scottblydotcom/tap` |

---

## Task 1: Extractor — parse single-line command from a subsection

**Files:**
- Create: `scripts/extract_install_commands.py`
- Create: `tests/unit/test_extract_install_commands.py`
- Create: `tests/fixtures/install_readmes/minimal_pipx.md`

- [ ] **Step 1: Create the fixture README**

Create `tests/fixtures/install_readmes/minimal_pipx.md` with:

```markdown
# Some Project

Intro text.

## Install

Recommended (via pipx):

```bash
pipx install hermia
```

## Something else

Unrelated.
```

Note: the ``` fences above are LITERAL content in the fixture file — the file itself contains those three backticks. Save the file with the fences included.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_extract_install_commands.py`:

```python
from pathlib import Path

from scripts.extract_install_commands import extract_install_commands

FIXTURES = Path(__file__).parent.parent / "fixtures" / "install_readmes"


def test_extract_pipx_from_minimal_readme():
    result = extract_install_commands(
        readme_path=FIXTURES / "minimal_pipx.md",
        expected_methods=("pipx",),
    )
    assert result == {"pipx": ["pipx install hermia"]}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_extract_install_commands.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract_install_commands'`

- [ ] **Step 4: Add __init__ so scripts is importable**

Create `scripts/__init__.py` as an empty file.

- [ ] **Step 5: Write the extractor's first cut**

Create `scripts/extract_install_commands.py`:

```python
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/test_extract_install_commands.py -v --no-cov`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/extract_install_commands.py \
        tests/unit/test_extract_install_commands.py \
        tests/fixtures/install_readmes/minimal_pipx.md
git commit -m "feat(hermia-02d): extractor happy path for pipx install command"
```

---

## Task 2: Extractor — multi-line commands (source install)

**Files:**
- Create: `tests/fixtures/install_readmes/source_install.md`
- Modify: `tests/unit/test_extract_install_commands.py`

The `source` install command in README.md spans three lines (`git clone`, `cd hermia`, `pip install -e .`). Task 1 already returns non-blank lines as a list, so this may already work. This task adds a test that pins that behavior against a fixture close to the real README.

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/install_readmes/source_install.md`:

```markdown
## Install

Or from source:

```bash
git clone https://github.com/scottblydotcom/hermia
cd hermia
pip install -e .
```
```

(Same reminder as Task 1: the ``` fences are literal content in the fixture.)

- [ ] **Step 2: Add the failing test**

Append to `tests/unit/test_extract_install_commands.py`:

```python
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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_extract_install_commands.py -v --no-cov`
Expected: PASS (Task 1's implementation already handles multi-line blocks).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_extract_install_commands.py \
        tests/fixtures/install_readmes/source_install.md
git commit -m "test(hermia-02d): pin multi-line command extraction for source install"
```

---

## Task 3: Extractor — full happy path against a real-README fixture

**Files:**
- Create: `tests/fixtures/install_readmes/full_readme.md`
- Modify: `tests/unit/test_extract_install_commands.py`

- [ ] **Step 1: Create the full fixture**

Create `tests/fixtures/install_readmes/full_readme.md`. This mirrors the real README's `## Install` section shape closely, including the intentionally-fixed tap name (`scottblydotcom/tap`):

```markdown
# Hermia

Some intro.

## Install

Recommended (via pipx):

```bash
pipx install hermia
```

Or via Homebrew (macOS):

```bash
brew install scottblydotcom/tap/hermia
```

Or with pip:

```bash
pip install hermia
```

Or from source:

```bash
git clone https://github.com/scottblydotcom/hermia
cd hermia
pip install -e .
```

Or via Docker (headless fleet mode):

```bash
mkdir -p results && chmod 777 results
docker run --rm --network host \
  -v $PWD/fleets:/workspace/fleets:ro \
  -v $PWD/results:/workspace/results \
  ghcr.io/scottblydotcom/hermia:latest \
  --fleet fleets/local.yaml
```

## Quickstart

Something else.
```

(Backtick fences are literal.)

- [ ] **Step 2: Add the failing test**

Append to `tests/unit/test_extract_install_commands.py`:

```python
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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_extract_install_commands.py -v --no-cov`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_extract_install_commands.py \
        tests/fixtures/install_readmes/full_readme.md
git commit -m "test(hermia-02d): full-fixture happy path for all five install methods"
```

---

## Task 4: Extractor — strict-mode failures

**Files:**
- Create: `tests/fixtures/install_readmes/missing_install_section.md`
- Create: `tests/fixtures/install_readmes/missing_pipx_heading.md`
- Create: `tests/fixtures/install_readmes/pipx_no_code_fence.md`
- Modify: `tests/unit/test_extract_install_commands.py`

- [ ] **Step 1: Create the three failure-mode fixtures**

`tests/fixtures/install_readmes/missing_install_section.md`:

```markdown
# Hermia

## Quickstart

No install section here.
```

`tests/fixtures/install_readmes/missing_pipx_heading.md`:

```markdown
## Install

Or with pip:

```bash
pip install hermia
```
```

`tests/fixtures/install_readmes/pipx_no_code_fence.md`:

```markdown
## Install

Recommended (via pipx):

You would run `pipx install hermia`. But there is no bash block.
```

(Fences in the pip subsection of `missing_pipx_heading.md` are literal.)

- [ ] **Step 2: Add three failing tests**

Append to `tests/unit/test_extract_install_commands.py`:

```python
import pytest

from scripts.extract_install_commands import ExtractionError


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
```

Note: `pytest` import goes at the top of the file with other imports; it isn't already there from earlier tasks.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_extract_install_commands.py -v --no-cov`
Expected: PASS (all three strict-mode tests, plus the earlier happy-path tests)

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_extract_install_commands.py \
        tests/fixtures/install_readmes/missing_install_section.md \
        tests/fixtures/install_readmes/missing_pipx_heading.md \
        tests/fixtures/install_readmes/pipx_no_code_fence.md
git commit -m "test(hermia-02d): extractor strict-mode failure diagnostics"
```

---

## Task 5: Extractor — CLI wrapper

**Files:**
- Modify: `scripts/extract_install_commands.py`
- Modify: `tests/unit/test_extract_install_commands.py`

The workflow calls this script from a shell step and expects JSON on stdout. Add a `main()` and `if __name__ == "__main__":` block that takes `--readme`, `--method`, and prints commands as JSON.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_extract_install_commands.py`:

```python
import json
import subprocess
import sys


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_extract_install_commands.py::test_cli_emits_json_for_one_method -v --no-cov`
Expected: FAIL — either "No module named scripts.extract_install_commands" as `__main__` (running as a module), or JSONDecodeError.

- [ ] **Step 3: Add the CLI to the extractor**

Append to `scripts/extract_install_commands.py`:

```python
import argparse
import json
import sys


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_extract_install_commands.py -v --no-cov`
Expected: PASS (all tests)

- [ ] **Step 5: Manually verify against the real README**

Run: `python -m scripts.extract_install_commands --readme README.md --method pipx`
Expected: `["pipx install hermia"]`

Run: `python -m scripts.extract_install_commands --readme README.md --method brew`
Expected: `["brew install scottbly/tap/hermia"]` (the broken value — Task 6 fixes this).

- [ ] **Step 6: Commit**

```bash
git add scripts/extract_install_commands.py tests/unit/test_extract_install_commands.py
git commit -m "feat(hermia-02d): CLI wrapper emits JSON per install method"
```

---

## Task 6: Fix the README brew tap typo

**Files:**
- Modify: `README.md:145`

- [ ] **Step 1: Confirm the current state**

Run: `grep -n "scottbly/tap\|scottblydotcom/tap" README.md`
Expected: line 145 contains `brew install scottbly/tap/hermia` (the bug).

- [ ] **Step 2: Fix the typo**

Change line 145 in `README.md` from:

```bash
brew install scottbly/tap/hermia
```

to:

```bash
brew install scottblydotcom/tap/hermia
```

- [ ] **Step 3: Verify the extractor now returns the fixed value**

Run: `python -m scripts.extract_install_commands --readme README.md --method brew`
Expected: `["brew install scottblydotcom/tap/hermia"]`

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(hermia-02d): fix homebrew tap owner in install command

The README instructed 'brew install scottbly/tap/hermia' but the actual
tap is scottblydotcom/tap. Users copy-pasting the documented command hit
a 'no such tap' error. Discovered while wiring the docs-as-tested matrix
that would have caught this automatically."
```

---

## Task 7: Workflow — pip leg (single job, prove the concept)

**Files:**
- Create: `.github/workflows/docs-as-tested.yml`

Start with one leg only (pip on ubuntu-latest, Python 3.12). Once green, subsequent tasks fan out.

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/docs-as-tested.yml`:

```yaml
name: Docs as tested

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  pip:
    name: pip (${{ matrix.os }}, py${{ matrix.python-version }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest]
        python-version: ["3.12"]
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Extract install commands
        id: extract
        run: |
          set -euo pipefail
          commands_json="$(python -m scripts.extract_install_commands --readme README.md --method pip)"
          echo "commands=$commands_json" >> "$GITHUB_OUTPUT"
          echo "$commands_json"

      - name: Run install commands
        working-directory: ${{ runner.temp }}
        run: |
          set -euo pipefail
          echo '${{ steps.extract.outputs.commands }}' \
            | python -c "import json,sys; [print(c) for c in json.load(sys.stdin)]" \
            | while IFS= read -r cmd; do
                echo "+ $cmd"
                eval "$cmd"
              done

      - name: Assert hermia --version succeeds
        run: hermia --version

      - name: Assert hermia --help contains usage
        run: hermia --help | grep -q "usage: hermia"

      - name: Assert version matches PyPI's currently-published version
        run: |
          set -euo pipefail
          published="$(python -c 'import urllib.request,json; print(json.loads(urllib.request.urlopen("https://pypi.org/pypi/hermia/json").read())["info"]["version"])')"
          installed="$(hermia --version | awk '{print $NF}')"
          echo "PyPI info.version=$published, installed hermia --version=$installed"
          [ "$installed" = "$published" ]
```

- [ ] **Step 2: Sanity-check the workflow YAML syntax locally**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/docs-as-tested.yml'))"`
Expected: no exception. If pyyaml isn't installed system-wide, install with `pip install pyyaml` in a scratch venv first.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docs-as-tested.yml
git commit -m "ci(hermia-02d): docs-as-tested workflow with pip leg (ubuntu, py3.12)"
```

- [ ] **Step 4: Push and verify the pip leg passes on GitHub**

**HALT:** Do NOT push automatically — Scott's rule is that git pushes are Scott's call. Report to Scott: "Task 7 complete. Push the branch to trigger CI and verify the pip leg passes green before proceeding to Task 8." Wait for confirmation before moving on.

---

## Task 8: Workflow — expand pip leg to full (OS × Python) matrix

**Files:**
- Modify: `.github/workflows/docs-as-tested.yml`

- [ ] **Step 1: Expand the matrix**

In `.github/workflows/docs-as-tested.yml`, change the `pip.strategy.matrix` block from:

```yaml
      matrix:
        os: [ubuntu-latest]
        python-version: ["3.12"]
```

to:

```yaml
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.11", "3.12", "3.13"]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/docs-as-tested.yml
git commit -m "ci(hermia-02d): pip leg — expand to (ubuntu+macos) × (py3.11+3.12+3.13)"
```

- [ ] **Step 3: Push and verify all 6 pip jobs pass green on GitHub**

**HALT:** Do NOT push. Report: "Task 8 complete. Push and verify 6 pip jobs pass before Task 9." Wait for confirmation.

---

## Task 9: Workflow — add pipx leg

**Files:**
- Modify: `.github/workflows/docs-as-tested.yml`

- [ ] **Step 1: Add the pipx job**

Under `jobs:`, add after the `pip:` job (and before any later job):

```yaml
  pipx:
    name: pipx (${{ matrix.os }}, py${{ matrix.python-version }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install pipx
        run: |
          python -m pip install --upgrade pip
          python -m pip install pipx
          python -m pipx ensurepath

      - name: Extract install commands
        id: extract
        run: |
          set -euo pipefail
          commands_json="$(python -m scripts.extract_install_commands --readme README.md --method pipx)"
          echo "commands=$commands_json" >> "$GITHUB_OUTPUT"
          echo "$commands_json"

      - name: Run install commands
        working-directory: ${{ runner.temp }}
        run: |
          set -euo pipefail
          echo '${{ steps.extract.outputs.commands }}' \
            | python -c "import json,sys; [print(c) for c in json.load(sys.stdin)]" \
            | while IFS= read -r cmd; do
                echo "+ $cmd"
                eval "$cmd"
              done

      - name: Ensure pipx shim on PATH for this shell
        run: echo "$HOME/.local/bin" >> "$GITHUB_PATH"

      - name: Assert hermia --version succeeds
        run: hermia --version

      - name: Assert hermia --help contains usage
        run: hermia --help | grep -q "usage: hermia"

      - name: Assert version matches PyPI's currently-published version
        run: |
          set -euo pipefail
          published="$(python -c 'import urllib.request,json; print(json.loads(urllib.request.urlopen("https://pypi.org/pypi/hermia/json").read())["info"]["version"])')"
          installed="$(hermia --version | awk '{print $NF}')"
          echo "PyPI info.version=$published, installed hermia --version=$installed"
          [ "$installed" = "$published" ]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/docs-as-tested.yml
git commit -m "ci(hermia-02d): pipx leg — (ubuntu+macos) × (py3.11+3.12+3.13)"
```

- [ ] **Step 3: Push and verify all 6 pipx jobs pass on GitHub**

**HALT:** Do NOT push. Report: "Task 9 complete. Push and verify 6 pipx jobs pass before Task 10." Wait for confirmation.

---

## Task 10: Workflow — add source leg

**Files:**
- Modify: `.github/workflows/docs-as-tested.yml`

The source leg is unique: the extracted commands do `git clone ...`, `cd hermia`, `pip install -e .`. But the workflow already has the repo checked out at `$GITHUB_WORKSPACE`, and the `git clone` command in the README always clones the `main` branch of the public repo — which for a PR job would be the wrong tree. Two options: (a) run `git clone` literally as the README says (tests the published `main` state), or (b) recognize that from-source install means "install the code you have" and use the workspace checkout.

Per spec §Scope, the from-source leg is the one leg that tests the *current checkout* rather than a published artifact. Option (b) is the honest read. The compromise: run the extracted commands verbatim but redirect `git clone` to a scratch dir and swap `cd hermia` to use the workspace tree instead. Simpler: skip the extracted `git clone` and `cd hermia`, and just execute the last extracted command (`pip install -e .`) from `$GITHUB_WORKSPACE`.

The workflow acknowledges this deviation with a comment. From a "docs-as-tested" standpoint, the README is asserting *the shape* of the from-source flow: clone, cd, editable-install. We test the editable-install step against the current checkout because that's what "install this branch's code" means.

- [ ] **Step 1: Add the source job**

Under `jobs:`, add after the `pipx:` job:

```yaml
  source:
    name: source (${{ matrix.os }}, py${{ matrix.python-version }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Extract install commands (informational — asserted below)
        id: extract
        run: |
          set -euo pipefail
          commands_json="$(python -m scripts.extract_install_commands --readme README.md --method source)"
          echo "$commands_json"
          echo "commands=$commands_json" >> "$GITHUB_OUTPUT"

      - name: Assert extracted commands still have the expected shape
        run: |
          set -euo pipefail
          python <<'PY'
          import json, os
          commands = json.loads(os.environ["COMMANDS"])
          assert len(commands) == 3, commands
          assert commands[0].startswith("git clone"), commands[0]
          assert commands[1] == "cd hermia", commands[1]
          assert commands[2] == "pip install -e .", commands[2]
          PY
        env:
          COMMANDS: ${{ steps.extract.outputs.commands }}

      - name: Run editable install of the current checkout
        run: pip install -e .

      - name: Assert hermia --version succeeds
        run: hermia --version

      - name: Assert hermia --help contains usage
        run: hermia --help | grep -q "usage: hermia"

      - name: Assert version matches pyproject.toml
        run: |
          set -euo pipefail
          declared="$(python -c 'import tomllib; print(tomllib.loads(open("pyproject.toml").read())["project"]["version"])')"
          installed="$(hermia --version | awk '{print $NF}')"
          echo "pyproject.toml version=$declared, installed hermia --version=$installed"
          [ "$installed" = "$declared" ]
```

`tomllib` is stdlib in Python 3.11+; the matrix's Python versions all include it.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/docs-as-tested.yml
git commit -m "ci(hermia-02d): source leg — asserts README shape, installs current checkout"
```

- [ ] **Step 3: Push and verify all 6 source jobs pass on GitHub**

**HALT:** Do NOT push. Report: "Task 10 complete. Push and verify 6 source jobs pass before Task 11." Wait for confirmation.

---

## Task 11: Workflow — add brew leg

**Files:**
- Modify: `.github/workflows/docs-as-tested.yml`

The brew leg runs only on `macos-latest` and needs no Python matrix — the formula pins `python@3.12`. It must add the tap before running `brew install`, but only if the README's extracted command doesn't include a `brew tap` step (currently it doesn't; only `brew install scottblydotcom/tap/hermia`). Homebrew's shorthand `owner/tap/formula` implicitly taps if needed, so no explicit `brew tap` is required.

- [ ] **Step 1: Add the brew job**

Under `jobs:`, add after the `source:` job:

```yaml
  brew:
    name: brew (macos-latest, formula-pinned python@3.12)
    runs-on: macos-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python (for the extractor)
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Extract install commands
        id: extract
        run: |
          set -euo pipefail
          commands_json="$(python -m scripts.extract_install_commands --readme README.md --method brew)"
          echo "commands=$commands_json" >> "$GITHUB_OUTPUT"
          echo "$commands_json"

      - name: Run install commands
        working-directory: ${{ runner.temp }}
        run: |
          set -euo pipefail
          echo '${{ steps.extract.outputs.commands }}' \
            | python -c "import json,sys; [print(c) for c in json.load(sys.stdin)]" \
            | while IFS= read -r cmd; do
                echo "+ $cmd"
                eval "$cmd"
              done

      - name: Assert hermia --version succeeds
        run: hermia --version

      - name: Assert hermia --help contains usage
        run: hermia --help | grep -q "usage: hermia"

      - name: Assert version matches PyPI's currently-published version
        run: |
          set -euo pipefail
          published="$(python -c 'import urllib.request,json; print(json.loads(urllib.request.urlopen("https://pypi.org/pypi/hermia/json").read())["info"]["version"])')"
          installed="$(hermia --version | awk '{print $NF}')"
          echo "PyPI info.version=$published, installed hermia --version=$installed"
          [ "$installed" = "$published" ]
```

If the brew formula lags behind PyPI (bump PR pending), this assertion legitimately fails and blocks the CI — that's the intended behavior per spec §Risks (brew-vs-PyPI drift is a real bug we want to surface).

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/docs-as-tested.yml
git commit -m "ci(hermia-02d): brew leg — macos-latest, formula-pinned python@3.12"
```

- [ ] **Step 3: Push and verify the brew job passes on GitHub**

**HALT:** Do NOT push. Report: "Task 11 complete. Push and verify the brew job passes before Task 12." Wait for confirmation.

---

## Task 12: Workflow — add docker leg

**Files:**
- Modify: `.github/workflows/docs-as-tested.yml`

Per spec §Docker leg — a documented deviation from literal execution, this leg does NOT execute the extracted `--fleet fleets/local.yaml` command (no Ollama backend in CI). Instead: extract, parse the image reference out of the extracted command, and run `docker run --rm <image> --version` / `--help`.

- [ ] **Step 1: Add the docker job**

Under `jobs:`, add after the `brew:` job:

```yaml
  docker:
    name: docker (ubuntu-latest, image-pinned python)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python (for the extractor)
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Extract install commands
        id: extract
        run: |
          set -euo pipefail
          commands_json="$(python -m scripts.extract_install_commands --readme README.md --method docker)"
          echo "commands=$commands_json" >> "$GITHUB_OUTPUT"
          echo "$commands_json"

      - name: Parse image reference from extracted docker command
        id: image
        env:
          COMMANDS: ${{ steps.extract.outputs.commands }}
        run: |
          set -euo pipefail
          image="$(python <<'PY'
          import json, os, re, sys
          commands = json.loads(os.environ["COMMANDS"])
          joined = " ".join(commands)
          match = re.search(r"(ghcr\.io/[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+)", joined)
          if match is None:
              print("could not find ghcr.io image reference in extracted docker command", file=sys.stderr)
              sys.exit(1)
          print(match.group(1))
          PY
          )"
          echo "ref=$image" >> "$GITHUB_OUTPUT"
          echo "image=$image"

      - name: Assert hermia --version succeeds inside the image
        run: docker run --rm ${{ steps.image.outputs.ref }} --version

      - name: Assert hermia --help contains usage
        run: docker run --rm ${{ steps.image.outputs.ref }} --help | grep -q "usage: hermia"

      - name: Assert version matches PyPI's currently-published version
        run: |
          set -euo pipefail
          published="$(python -c 'import urllib.request,json; print(json.loads(urllib.request.urlopen("https://pypi.org/pypi/hermia/json").read())["info"]["version"])')"
          installed="$(docker run --rm ${{ steps.image.outputs.ref }} --version | awk '{print $NF}')"
          echo "PyPI info.version=$published, image hermia --version=$installed"
          [ "$installed" = "$published" ]
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/docs-as-tested.yml
git commit -m "ci(hermia-02d): docker leg — narrowed to image + entrypoint verification"
```

- [ ] **Step 3: Push and verify the docker job passes on GitHub**

**HALT:** Do NOT push. Report: "Task 12 complete. Push and verify the docker job passes before Task 13." Wait for confirmation.

---

## Task 13: End-to-end validation + bead close

**Files:** None modified.

- [ ] **Step 1: Confirm all 20 jobs went green on the most recent push**

Run: `gh run list --workflow=docs-as-tested.yml --limit 1 --json conclusion,name`
Expected: `conclusion` is `success`.

Run: `gh run view --log-failed` if the above shows failure — do not proceed until 20/20 green.

- [ ] **Step 2: Deliberately break the README locally to prove the matrix catches drift**

- Save the current README.md aside: `cp README.md /tmp/README.md.good`
- Revert the tap-owner fix: `sed -i.bak 's|scottblydotcom/tap|scottbly/tap|' README.md && rm README.md.bak`
- Confirm the extractor returns the broken value: `python -m scripts.extract_install_commands --readme README.md --method brew`
- Expected: `["brew install scottbly/tap/hermia"]`
- Restore the good README: `cp /tmp/README.md.good README.md`

**Do not commit or push the broken state.** This step is local proof only.

- [ ] **Step 3: Close the bead**

Run: `bd close hermia-02d`
Then, `bd note hermia-02d "20-job matrix green on <commit-sha>. Extractor + workflow shipped in <PR-URL>. README brew-tap typo fix included in same PR (line 145: scottbly → scottblydotcom). Deferred: hermia-9ff (snippet-file source-of-truth pattern) and hermia-0sc (Windows platform support)."`

- [ ] **Step 4: Report the state to Scott**

Report: "hermia-02d shipped. 20/20 matrix jobs green. README typo fixed inside the same PR (line 145 tap-owner). Bead closed. hermia-4e8 (v0.2.0 cut) is now unblocked from the docs-as-tested angle. Deferred: hermia-9ff and hermia-0sc."
