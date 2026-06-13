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

```bash
# Point Hermia at your pAI-OS Ollama backend (this is the default host).
hermia --host http://localhost:11434
```

Hermia auto-discovers the models installed on that Ollama instance and runs the
corpus against each. Results land in `results/eval_*.{jsonl,csv}`.

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

`hermia-submit` anonymizes the payload (no usernames, no raw hostnames) before
sending it to the live endpoint (`https://hermia.scottbly.com`). On success it
prints a public URL where your submission renders.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `hermia: command not found` | `pipx ensurepath`, reopen shell |
| openai-compat host "requires an explicit 'models:' list" | add `models: auto` (or an explicit list) to the entry |
| `/v1/models` returns nothing | confirm `kwaainet shard api` is up on `:11435` and a model is loaded |
| Discovery failed, host skipped | the endpoint was unreachable or returned a malformed `/v1/models` — re-check step 2 |
