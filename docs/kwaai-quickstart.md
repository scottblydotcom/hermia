# Hermia + Kwaai — Quickstart

Hermia evaluates the safety and capability of self-hosted models. This guide gets
a Kwaai user from install to a submitted result on two paths:

- **Path A — pAI-OS** (the easy default): your local Ollama backend on `:11434`.
- **Path B — KwaaiNet**: distributed, block-sharded inference over the network.

Both end with submitting your result to the public community dataset.

---

## Install

```bash
pipx install hermia      # or: pip install hermia
```

If `hermia` isn't found afterward, run `pipx ensurepath` and reopen your shell.

---

## Path A — pAI-OS (Ollama on :11434)

pAI-OS runs its inference backend as Ollama on port `11434`, which is **Hermia's
native default target** — no config file needed.

Run Hermia with no arguments. It opens a terminal UI:

```bash
hermia
```

From the launch screen, choose **Quick local run**. That pre-fills the host as
`http://localhost:11434` (Ollama) and selects the full test corpus, so the only
thing left to choose is which models to evaluate:

1. **Quick local run** on the launch screen.
2. On the config screen, open the host's model list — Hermia probes
   `GET /api/tags` and shows what pAI-OS actually has installed.
3. Select one or more models, then start the run.
4. Watch verdicts land per trial; drill into any row for the full response.

Each run writes its own file: **`results/eval_<run_id>.jsonl`** (and `.csv`) —
the same directory and naming the fleet path uses, so every Hermia tool finds it.

---

## Path B — KwaaiNet (distributed inference)

KwaaiNet serves an OpenAI-compatible endpoint (`/v1`), not Ollama's `/api`, so
this path uses a fleet config with `transport: openai-compat`.

### 1. Bring your node online

```bash
kwaainet start --daemon
kwaainet status            # wait for 🟢 online
kwaainet shard chain       # confirm fast nodes (metro-linux / metro-win) are present
```

### 2. Start the OpenAI endpoint

```bash
kwaainet shard api --port 11435
# Use 11435 — NOT 8080 (collides with the p2pd daemon / node config).
curl http://localhost:11435/v1/models     # should list your model id
```

### 3. Run Hermia against it

A ready-to-use config ships in the repo at `examples/kwaainet-fleet.yaml`. It uses
`models: auto`, which discovers the served model via `GET /v1/models` — no need to
hand-type the (long) model id.

```bash
hermia --fleet examples/kwaainet-fleet.yaml --verbose --max-concurrency 1
```

**Caveats (as of 2026-06):**
- At relay speed (~2.3 t/s) the full 28-test corpus takes ~30 min. Run subsets or
  let it run in the background.
- `kwaainet shard api` cannot pin which node answers (no `--name-filter` on the
  HTTP path) — it picks a circuit per request. For a guaranteed fast-node single
  inference, use `kwaainet shard run "..." --name-filter metro-linux` directly.

---

## Submit your result

Once you have a results file, contribute it to the public dataset:

```bash
hermia-submit --dry-run     # inspect the anonymized payload — no network I/O
hermia-submit               # submit (prompts for confirmation; --yes to skip)
```

With no `--results`, `hermia-submit` uses the most recent results file — which
is the run you just finished, on either path. Pass `--results <file>` to submit
a specific one.

`hermia-submit` anonymizes the payload (no usernames, no raw hostnames) before
sending it to the live endpoint (`https://hermia.scottbly.com`). On success it
prints a public URL where your submission renders.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `hermia: command not found` | `pipx ensurepath`, reopen shell |
| `unrecognized arguments: --host` | There is no `--host` flag. Run bare `hermia` and pick **Quick local run** (Path A). |
| `--repeat/--verbose can only be used with --fleet` | Those flags are fleet-mode only; set repeats inside the TUI or use `--fleet` |
| openai-compat host "requires an explicit 'models:' list" | add `models: auto` (or an explicit list) to the entry |
| `/v1/models` returns nothing | confirm `kwaainet shard api` is up on `:11435` and a model is loaded |
| Discovery failed, host skipped | the endpoint was unreachable or returned a malformed `/v1/models` — re-check step 2 |
