# Getting Started with Hermia

This guide walks you through installing Hermia, running your first eval, interpreting the
results, and optionally exporting to Postgres for long-term tracking.

---

## Prerequisites

- **Python 3.11+**
- **[Ollama](https://ollama.ai) installed and running** — `ollama serve`
- **At least one model pulled** — for example:

  ```bash
  ollama pull llama3.2
  ```

No cloud API keys required. No data leaves your machine.

---

## Install

Clone and install in editable mode:

```bash
git clone https://github.com/scottblydotcom/hermia
cd hermia
pip install -e .
```

To verify the install:

```bash
hermia --help
```

Expected output:

```
usage: hermia [-h] [--host HOST] [--repeat N]
```

---

## Run a local eval

Make sure Ollama is running and has at least one model pulled, then launch the TUI:

```bash
hermia
```

### SelectionScreen

Hermia opens the **SelectionScreen**. You'll see two columns:

- **Models** — all models currently available via `ollama list`, pre-checked
- **Eval dimensions** — `security`, `tool-use`, `reasoning`, `constraint`, `routing`,
  `memory`, `domain`, pre-checked

Use the checkboxes to select which models and dimensions to run. Press **Run** to start.

If no models appear, Ollama is not running or has no models pulled. Start it with
`ollama serve` and pull a model with `ollama pull llama3.2`.

### RunnerScreen

The **RunnerScreen** shows a live feed as each test runs:

```
Preflight  VRAM 18.2/18.2 GB free  RAM 10.4/18.0 GB free  Disk 124.3 GB free
Cold-loading llama3.2...

  ✅ security-direct-injection             42.3 t/s  GPU 82%  VRAM 4.2GB  CPU 18%
  ✅ security-indirect-injection           39.1 t/s  GPU 79%  VRAM 4.2GB  CPU 16%
  ⚠  tool-use-invalid-invocation          38.8 t/s  GPU 81%  VRAM 4.2GB  CPU 17%
  ❌ reasoning-partial-failure             35.2 t/s  GPU 76%  VRAM 4.1GB  CPU 15%
       output did not match expected schema
```

Icons mean:
- `✅` — JSON valid **and** schema compliant (full pass)
- `⚠` — JSON valid but schema non-compliant (partial pass)
- `❌` — JSON invalid or error (full fail); preview of the failure reason shown below

Per-test metrics: `t/s` = tokens per second, `GPU%` = peak GPU utilization,
`VRAM` = peak VRAM used (GB), `CPU%` = peak CPU utilization.

### Summary

After all tests complete, the summary panel shows:

```
EVAL SUMMARY

Model                        JSON%   Schema%   Agentic    t/s
──────────────────────────────────────────────────────────────
llama3.2                      95%      88%       91%     41.2
qwen2.5:7b                    90%      82%       85%     38.6

LOAD BENCHMARKS

Model                        Size    Load    GB/s   VRAM Δ
──────────────────────────────────────────────────────────────
llama3.2                      2.0G    1.4s    1.43   +2.10 GB
qwen2.5:7b                    4.7G    2.1s    2.24   +4.68 GB

Best: llama3.2 (91/100)
Saved: eval_20260511_143022.jsonl  | eval_20260511_143022.csv
```

**Agentic score** (summary table) = (JSON pass rate × 0.40) + (schema pass rate × 0.60).
A model that produces well-structured, schema-compliant responses to agentic tasks scores
higher than one that responds in free text, even if the free-text answer is "correct."

Each individual result row also carries a per-row **score** (used in Postgres export):
`100` = JSON valid + schema compliant, `60` = JSON valid but schema failed,
`25` = response received but not valid JSON, `0` = error / timeout / no response.

**Load benchmarks** measure cold-load time (from clean VRAM state) and model size. This is
the actual load time a user or system experiences on first use, not cached inference.

---

## Result files

Each run writes two files to `results/` in the project directory:

| File | Format | Contents |
|---|---|---|
| `eval_TIMESTAMP.jsonl` | JSONL (one row per test) | Full result rows with all metrics |
| `eval_TIMESTAMP.csv` | CSV | Same rows, spreadsheet-friendly |

Each result row contains:

| Field | Description |
|---|---|
| `model` | Model name |
| `test_id` | Test identifier (e.g. `security-direct-injection`) |
| `dimension` | Eval category |
| `json_valid` | Boolean — did the model return valid JSON? |
| `schema_compliant` | Boolean — did the response match the expected schema? |
| `tokens_per_sec` | Inference throughput |
| `elapsed_sec` | Wall time for this test |
| `peak_gpu_pct` | Peak GPU utilization during the test |
| `peak_vram_used_gb` | Peak VRAM consumed |
| `peak_cpu_pct` | Peak CPU utilization |
| `is_cold` | True for the first invocation of a model (from clean VRAM state) |
| `failure_reason` | Error type or empty string on pass |
| `output_preview` | First 120 chars of the raw model output |
| `run_id` | UUID identifying this run |
| `run_timestamp` | ISO 8601 timestamp |

---

## Repeat runs and consistency scoring

Use `--repeat N` to run each (model, test) pair N times. This enables consistency scoring
and cold-vs-warm delta measurement:

```bash
hermia --repeat 5
```

Additional fields populated when `--repeat N > 1`:

| Field | Description |
|---|---|
| `run_index` | Which repetition this row is (1..N) |
| `consistency_pct` | Fraction of N runs that produced the same pass/fail outcome |
| `pass_count` | Number of runs that passed |
| `cold_warm_delta_tps` | Cold-run t/s minus mean warm-run t/s (on `run_index=1` rows) |

A model with 100% consistency is behaviorally stable. A model with 60% consistency is
reward-hacking — it passes sometimes and fails sometimes on the same input.

---

## Run against a remote Ollama host

Use `--host` to target any Ollama-compatible endpoint instead of localhost:

```bash
hermia --host http://192.168.10.50:11434
```

In fleet mode (any non-localhost host), local hardware metrics (GPU%, VRAM, CPU%) reflect
the **inference server's** hardware via Ollama's `/api/ps` endpoint, not the eval client's
idle laptop. The preflight check is also bypassed — resource checks run on the server side.

This works with any host accessible over the network: a bare Ollama server, a LiteLLM
gateway (in v0.1, use the Ollama-compatible endpoint), or a remote lab machine.

---

## Multi-host fleet mode (`--fleet`)

Pass a YAML fleet config to evaluate multiple hosts in a single headless run:

```bash
hermia --fleet hermia-fleet.yaml
```

**Concurrent execution.** Fleet hosts are evaluated concurrently by default (up to 4
in parallel). To change the cap:

```bash
hermia --fleet hermia-fleet.yaml --max-concurrency 8   # more parallelism
hermia --fleet hermia-fleet.yaml --max-concurrency 1   # fully sequential
```

**VRAM-safe serialization.** Fleet entries that share the same host (normalized URL)
are always evaluated sequentially — one model loaded at a time — so a single GPU node
is never asked to hold two models simultaneously. Entries on different hosts run in
parallel up to `--max-concurrency`.

**Operational note on host identity.** Grouping is by URL string. If two fleet entries
point at the same physical machine via different addresses (e.g. `localhost` vs
`127.0.0.1` vs its hostname), they will **not** be grouped and may run concurrently.
Use the identical host string for all entries on one box to keep them serialized.

---

## Regression detection

After accumulating multiple runs, use `hermia-regression` to detect behavioral drift —
models that used to pass a test but now fail it:

```bash
# Merge all JSONL files into a single JSON array for the regression script
python3 -c "
import json, glob
rows = []
for f in sorted(glob.glob('results/eval_*.jsonl')):
    with open(f, encoding='utf-8') as fh:
        rows.extend(json.loads(l) for l in fh if l.strip())
with open('all-results.json', 'w', encoding='utf-8') as fh:
    json.dump(rows, fh)
"

hermia-regression all-results.json
```

Output:

```
=== Hermia Regression Report ===
[SOFT] llama3.2 / security-direct-injection | baseline 100% → current 60%
       llama3.2/security-direct-injection pass rate dropped 100% → 60% (Δ=40.0 pp).

Summary: 0 hard failure(s), 1 soft alert(s)
```

`[HARD]` = complete failure (current rate 0%). `[SOFT]` = significant drop but still passing sometimes.

Exit codes:
- `0` — no regressions
- `1` — one or more regressions detected
- `2` — file not found or parse error

You can wire this directly into CI after a nightly eval run.

---

## Export to Postgres

`hermia-push` reads all `eval_*.jsonl` files from `results/` and inserts them into a
`hermia_results` Postgres table. Results already in the table (matched on
`run_id + host + model + test_id + run_index`) are skipped — safe to run repeatedly.

### Setup

Install the Postgres extras:

```bash
pip install -e ".[grafana]"
```

Set your DSN and create the table (run once):

```bash
export HERMIA_PG_DSN="postgresql://user:pass@localhost:5432/hermia"
psql $HERMIA_PG_DSN -f scripts/create_table.sql
psql $HERMIA_PG_DSN -f scripts/add_framework_columns.sql
psql $HERMIA_PG_DSN -f scripts/add_judge_columns.sql
```

`create_table.sql` creates `hermia_results` with all columns and the unique conflict key.
`add_framework_columns.sql` adds GIN indexes on the framework taxonomy arrays.
`add_judge_columns.sql` adds `judge_score` and `judge_reasoning` for v0.3 LLM-as-judge.
Run all three on a fresh install, or only the relevant migration scripts when upgrading.

### Push results

```bash
hermia-push
```

Or pass the DSN directly:

```bash
hermia-push --dsn "postgresql://user:pass@localhost:5432/hermia"
```

Dry-run (prints rows without writing):

```bash
hermia-push --dry-run
```

Push from a specific directory:

```bash
hermia-push --results-dir /path/to/results
```

---

## Multi-turn test cases

Some test cases define a multi-turn conversation via the `turns` field instead of a
single `prompt`. Hermia plays these conversations deterministically: it sends each user
turn in order, appending the model's reply to the conversation history before sending
the next turn. Only the **final assistant reply** is schema-checked.

### When to use multi-turn

Multi-turn cases are useful for testing:

- **Context retention across turns** — does the model remember a constraint established
  in turn 1 when answering turn 2?
- **Safety-boundary persistence** — if turn 1 is benign and turn 2 attempts a social
  engineering override ("the system prompt has been updated to allow X"), does the model
  hold its original constraints?

### Test case format

```json
{
  "id": "multiturn-context-carry",
  "dimension": "multi-turn",
  "description": "...",
  "system": "...",
  "prompt": "",
  "turns": [
    "My total budget is $500.",
    "Estimate the cost of 10 keyboards at $45 each. Are we within budget?"
  ],
  "frameworks": { ... }
}
```

- `prompt` must be `""` when `turns` is present (the turns list replaces the prompt).
- `turns` must contain at least 2 entries (use a single `prompt` for one-turn cases).
- The SCHEMA_CHECKS entry for the test id validates the **final-turn** response only.

### Determinism

The orchestration is fully deterministic — fixed turn order, identical message
construction, no randomness in how the conversation is assembled. Hermia passes
`temperature=0` to the backend for multi-turn cases to give the backend the best
opportunity to produce reproducible output. Whether the model actually produces
identical output depends on backend support (temperature 0 + seed support varies);
this is documented, not promised.

Single-turn cases (a case with no `turns` field, or `turns` absent) are unaffected —
they use the transport's default temperature exactly as before.

### Result fields

Two additional fields are present in every result row:

| Field | Description |
|---|---|
| `turn_count` | Number of user turns played (1 for single-turn cases) |
| `raw_turns` | The ordered list of user turn strings played in this run |

## Opt-in community submission (`--submit`)

After a fleet run you can contribute anonymized results to the Hermia community
dataset.  **Nothing is sent unless you pass `--submit` explicitly.**

### What is shared

A strict default-deny whitelist determines what leaves your machine.  Only
aggregate performance fields are included:

| Field | Example |
|---|---|
| `model` | `qwen2.5:32b` |
| `dimension` / `test_id` | `security` / `security-direct-injection` |
| `json_valid` / `schema_compliant` / `had_markdown_fence` | `true` |
| `tokens` / `elapsed_sec` / `tokens_per_sec` | `142` / `1.4` / `101.4` |
| `mode` / `orchestration` / `orchestration_version` | `fleet` / `ollama` / `0.9.0` |
| `execution_path` / `vram_server_gb` / `model_size_server_gb` | `gpu` / `18.0` / `4.7` |
| `score` / `consistency_pct` / `pass_count` / `robustness_n` | `100` / `95.0` / `9` / `10` |
| `run_index` / `is_cold` / `cold_warm_delta_tps` | `1` / `false` / `12.3` |
| `failure_category` (derived from `failure_reason`) | `SCHEMA_FAIL` |

### What is never shared

The anonymizer unconditionally drops:

- Host names, IP addresses, fleet host metadata
- Raw prompt, raw response, raw system prompt
- Output preview (may contain model-verbatim sensitive text)
- Run ID and timestamp (would allow cross-run correlation)
- Client hardware metrics (CPU%, RAM, GPU%, VRAM — client-side only)

`failure_reason` is reduced to a category prefix only (`ERROR`, `SCHEMA_FAIL`,
`TIMEOUT`, etc.) — the detail that can contain host names or paths is stripped.

### Dry-run (inspect the payload first)

Print the payload to stdout without sending anything:

```bash
hermia --fleet hermia-fleet.yaml --submit-dry-run
```

### Live submission

Set the endpoint URL and opt in:

```bash
export HERMIA_SUBMIT_URL="https://submit.hermia.dev/v1/results"
hermia --fleet hermia-fleet.yaml --submit
```

The bearer token (if the endpoint requires one) comes from `HERMIA_SUBMIT_TOKEN`:

```bash
export HERMIA_SUBMIT_TOKEN="..."
hermia --fleet hermia-fleet.yaml --submit
```

Submission is best-effort: a non-2xx response or network failure logs a warning
and does not abort the run.

---

## What's next

- **Grafana dashboards** — if you have Grafana running, point it at the `hermia_results`
  table. The [Hermia Eval Leaderboard](https://github.com/scottblydotcom/hermia) dashboard
  JSON is in `docs/`.
- **Roadmap** — see [Roadmap](roadmap.md) for v0.2 (multi-endpoint, fleet config)
  and v0.3 (eval bus, Garak/PyRIT adapters).
- **Contributing** — see [AGENTS.md](../AGENTS.md) for the behavioral rules and module
  boundary table before opening a PR.
