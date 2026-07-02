---
bead: hermia-02d
title: Docs-as-tested CI matrix design
date: 2026-07-01
status: approved
---

# Docs-as-tested CI matrix design

## Problem

Hermia's `README.md` documents five ways to install: `pipx`, `brew`, `pip`, from-source, and `docker`. Today, none of these commands are automatically verified. When the README drifted (a `scottbly/tap` typo where it should read `scottblydotcom/tap`), no CI signal caught it — a user copy-pasting the documented command would hit a "no such tap" error.

Per the v0.2 roadmap, "docs cannot drift from reality." This bead makes the documented install commands executable in CI, so any README change that breaks an install path fails the build.

## Goal

A new GitHub Actions workflow runs the install commands extracted literally from `README.md` in clean, isolated environments across the platform + Python-version combinations Hermia claims to support. A red job means either the README is wrong or the published artifact is wrong; either way, a human decides what to fix.

## Scope

**In scope:** Install-time verification for the Python `hermia` package (pip, pipx, brew, docker, from-source), on macOS + Linux, on Python 3.11 / 3.12 / 3.13. Each leg runs the extracted command in a fresh runner and asserts the resulting `hermia --version` and `hermia --help` succeed.

**Out of scope:**
- Windows runners — tracked separately in [hermia-0sc](P2), gated on Windows platform support for the Hermia Python package.
- Snippet-file source-of-truth pattern — tracked separately in [hermia-9ff](P3) as a future refactor.
- Pre-release local-build install testing — the matrix tests published artifacts, which is what a user experiences. If we ever want a pre-release local-build gate, that's a separate bead.
- Launching the TUI or running evals — belongs to the existing `ci.yml` unit/integration suite, not this install-verification workflow.

## Design

### Triggers

- `pull_request` to `main`
- `push` to `main`

No scheduled cron. Weekly-drift scenarios (PyPI yanks, transitive dep breakage, brew core bumps) have a very low base rate, and users report them fast when they hit. Notification noise from scheduled failures is not worth the marginal coverage. If we ever see drift in the wild that would have been caught by a cron trigger, we add it then.

### README extraction

A new script `scripts/extract_install_commands.py` reads `README.md` and pulls the ```bash code blocks under each subsection of `## Install`. It emits a JSON map:

```json
{
  "pipx":   ["pipx install hermia"],
  "brew":   ["brew install scottblydotcom/tap/hermia"],
  "pip":    ["pip install hermia"],
  "source": ["git clone https://github.com/scottblydotcom/hermia", "cd hermia", "pip install -e ."],
  "docker": ["mkdir -p results && chmod 777 results", "docker run --rm --network host -v $PWD/fleets:/workspace/fleets:ro -v $PWD/results:/workspace/results ghcr.io/scottblydotcom/hermia:latest --fleet fleets/local.yaml"]
}
```

**Strict mode.** The extractor knows the expected set of install methods ahead of time (`pipx`, `brew`, `pip`, `source`, `docker`). If the README's `## Install` section is missing an expected method, contains an unexpected method, or has a subsection with no fenced `bash` block, extraction fails loudly with a diagnostic pointing at the specific mismatch. That's a feature — it forces the README structure and the matrix to stay in sync. Adding a new install method requires updating the extractor's allowlist in the same PR.

The extractor lives in `scripts/` (not `src/hermia/`) because it's build tooling, not part of the shipped package.

### Matrix legs

Twenty jobs total, split by whether the install method uses the host's Python:

**Host-Python legs (fan out over Python versions):**
| Method | OS runners | Python versions | Jobs |
|--------|------------|-----------------|------|
| `pip` | `ubuntu-latest`, `macos-latest` | 3.11, 3.12, 3.13 | 6 |
| `pipx` | `ubuntu-latest`, `macos-latest` | 3.11, 3.12, 3.13 | 6 |
| `source` | `ubuntu-latest`, `macos-latest` | 3.11, 3.12, 3.13 | 6 |

**Fixed-Python legs (install method provides its own Python):**
| Method | OS runner | Notes | Jobs |
|--------|-----------|-------|------|
| `brew` | `macos-latest` | Formula pins `python@3.12`. Host Python irrelevant. | 1 |
| `docker` | `ubuntu-latest` | Image bundles its own Python. `--network host` limits Docker to Linux runners. | 1 |

Python 3.13 is included even though `pyproject.toml` only classifies 3.11 + 3.12, because Hermia has C-extension dependencies (`psutil`, `pyyaml`, `charset-normalizer`) where installs can succeed on wheels but break from source on a new Python. The matrix gives us early signal for when to declare 3.13 support.

### Per-job flow

Every job follows the same shape:

1. **Set up environment.** Fresh runner. For host-Python legs, install the matrix Python version via `actions/setup-python`. For `brew`, `pipx`, `docker` legs, use the tools already available on the runner (or install via the extracted command itself for `pipx` on Linux, which sometimes needs `apt-get install pipx`).
2. **Extract commands.** Run `python scripts/extract_install_commands.py --method $METHOD` and capture stdout as an array of shell commands.
3. **Execute commands literally.** Run the extracted commands, in order, from a scratch working directory. Each command runs in the same shell context (`cd` from step 1 of the source leg has to affect step 2's `pip install -e .`).
4. **Assertions:**
   - `hermia --version` exits 0.
   - Version string matches expectations:
     - For `pip`, `pipx`, `brew`, `docker` legs → matches the currently-published version pulled from PyPI's JSON API (`https://pypi.org/pypi/hermia/json`, field `info.version`).
     - For `source` leg → matches `pyproject.toml`'s `[project].version`.
   - `hermia --help` exits 0 and contains the string `usage: hermia`.

### Docker leg — a documented deviation from literal execution

The docker leg has a real gap in the pure docs-as-tested principle, and this section documents it honestly.

The README's docker command is `docker run ... ghcr.io/scottblydotcom/hermia:latest --fleet fleets/local.yaml`. That command requires a live fleet backend (an Ollama server reachable from inside the container) to run to completion. CI runners have no such backend. If we ran the extracted command literally, the docker leg would always fail — not because the install is broken, but because there's no infrastructure to talk to.

The docker leg therefore verifies a **narrower claim**: "the ghcr.io image is pullable, the entrypoint runs `hermia`, and `hermia --version` succeeds inside the container." Specifically, the leg:

1. Extracts the docker command from README (proves the command is well-formed and points at a real image).
2. Parses out the image reference (`ghcr.io/scottblydotcom/hermia:latest`) from the extracted command.
3. Runs `docker run --rm <image> --version` and asserts success.
4. Optionally runs `docker run --rm <image> --help` and asserts `usage: hermia`.

We do **not** execute the full extracted `--fleet ...` command. This is a known trade-off: mocking a fake Ollama backend for a single install-verification leg is out of proportion to the bead's goal. If a future bead adds an integration test with a fake Ollama backend, that test can run the full command literally.

The other four legs (`pip`, `pipx`, `brew`, `source`) do run their extracted commands literally with no such deviation.

### README fix included in the same PR

`README.md:145` currently says `brew install scottbly/tap/hermia`. It should be `scottblydotcom/tap/hermia`. This bug is exactly what the matrix is designed to catch — fixing it inside the same PR proves the matrix works on its first green run.

## Files touched

**New:**
- `.github/workflows/docs-as-tested.yml`
- `scripts/extract_install_commands.py`
- `tests/unit/test_extract_install_commands.py` (unit tests for the extractor — golden-file tests against a fixture README, plus failure-mode tests for missing methods, missing code fences, unexpected methods)

**Modified:**
- `README.md` — fix `scottbly/tap` → `scottblydotcom/tap` (line 145).

## Success criteria

- All 20 matrix jobs pass green on the PR that introduces the workflow (with the README typo fixed).
- Deliberately breaking the README (e.g. reverting the `scottblydotcom/tap` fix, or corrupting a code fence) turns the corresponding job red on the next push.
- Adding a new install method to the README without updating the extractor allowlist fails the extractor with a clear diagnostic.

## Risks and mitigations

**Extractor fragility.** Markdown parsing is a genuinely fragile thing. Mitigation: keep the parser small and strict — one section (`## Install`), one code-fence type (```bash), one code block per subsection heading. Unit-tested against fixtures. If someone wants richer markdown-in-install-docs later, they can migrate to the snippet-file pattern ([hermia-9ff](P3)).

**Matrix cost.** Twenty jobs per PR run is significant. Mitigation: GitHub Actions is free for public repos; if we ever go private, we can trim the Python 3.11 legs first (least likely to break specifically vs. 3.12/3.13).

**Published-artifact drift between merge and release.** Between merging code and cutting a new release, the pip/pipx/brew/docker legs test the *previous* published version. If a merge changes behavior but the matrix keeps testing an old artifact, the matrix might stay green while the un-released code is broken. Mitigation: accepted trade-off. Testing published artifacts is what "docs correctness for users" means; the code correctness is covered by `ci.yml`'s unit tests. If we ever want pre-release install verification, that's a separate bead.

**Homebrew tap PATH ordering on GitHub's macOS runners.** GitHub's `macos-latest` runners have Homebrew pre-installed at `/opt/homebrew` (arm64) or `/usr/local` (x86_64) depending on runner architecture. The brew leg trusts whatever the runner ships and does not manipulate PATH. If a runner image change breaks this assumption, the leg goes red and we investigate then.
