# Getting Started with Hermia

Zero to your first eval in under 5 minutes. No accounts, no cloud, no API keys.

This guide is the fastest path. For the full reference (fleet mode, regression
detection, Postgres export, result schema) see [usage.md](usage.md).

---

## 1. Install Ollama

Hermia evaluates models served by [Ollama](https://ollama.ai). Install it first.

**macOS / Linux:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS (alternative):** download the installer from [ollama.com/download](https://ollama.com/download).

**Windows:** download the installer from [ollama.com/download](https://ollama.com/download). Hermia runs against Ollama on Windows as a fleet target, but running Hermia itself on Windows is not yet supported.

---

## 2. Start Ollama and pull a model

```bash
ollama serve &        # start the daemon in the background
ollama pull llama3.2  # ~2 GB; takes a minute on a decent connection
```

`llama3.2` is the recommended starter model: small, fast, runs on a laptop CPU
if you have no GPU. Pull whatever else you want to test the same way:
`ollama pull qwen2.5:7b`, `ollama pull mistral:7b`, etc.

Confirm it landed:

```bash
ollama list
```

You should see `llama3.2:latest` in the output.

---

## 3. Install Hermia

Recommended (isolated install via [pipx](https://pipx.pypa.io)):

```bash
pipx install hermia
```

Or with pip:

```bash
pip install hermia
```

Confirm the install:

```bash
hermia --version
```

---

## 4. Run your first eval

Launch Hermia:

```bash
hermia
```

You land on the **LaunchScreen**. Three entries:

- **Quick local run** — pre-fills a fleet pointed at your local Ollama with the full default test set
- **Load existing fleet** — for saved YAML configs (you don't have any yet)
- **New fleet** — for building a multi-host config from scratch

Press **↓** to highlight **Quick local run**, then **Enter**.

Hermia drops into the **FleetConfigScreen** with a localhost entry pre-filled.
You'll see five rows — hosts, models, tests, name, options. Press **r** to run.

The runner shows a live three-level drill view:

- **L1** — aggregate pass/fail/running counts per host
- **L2** — per-trial table for one host (press Enter on the host to drill in)
- **L3** — full prompt and model output for one trial (press Enter on a trial)

**Esc** walks back up. **q** quits.

---

## 5. Find your results

Each run writes two files to `results/` in your current directory:

```
results/eval_TIMESTAMP.jsonl  # one row per trial, full metrics
results/eval_TIMESTAMP.csv    # same rows, spreadsheet-friendly
```

Open the CSV in a spreadsheet to see at a glance: per-model pass rates, t/s
throughput, failure reasons. The JSONL has the full raw_prompt, raw_response,
and stack fingerprint per trial for audit purposes.

---

## What's next

- **More models?** Run `ollama pull <name>` for each, then re-run Hermia — they'll show up automatically on the next launch.
- **Multi-host?** See [Multi-host fleet mode](usage.md#multi-host-fleet-mode---fleet) in usage.md.
- **Track behavior over time?** See [Regression detection](usage.md#regression-detection) in usage.md.
- **Long-term storage?** See [Postgres export](usage.md#postgres-export) in usage.md.

---

## Troubleshooting

**No models listed in the TUI** — Ollama isn't running, or you haven't pulled a
model. Run `ollama serve` in another terminal, `ollama pull llama3.2`, and
relaunch Hermia.

**`hermia: command not found`** — `pipx` installs to `~/.local/bin` by default;
make sure that's on your `PATH`. `pipx ensurepath` will fix it.

**`Connection refused` against localhost:11434** — Ollama isn't running. Start
it with `ollama serve`.

**Tests timing out** — Larger / thinking-mode models (e.g. `qwen3:32b`,
`deepseek-r1`) need more than the default 90-second per-test budget. Bump it
with `--test-timeout 180` or set `test_timeout: 180` in the fleet YAML.
