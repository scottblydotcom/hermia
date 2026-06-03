# Hermia Workstreams — Active Branch Manifest

> **Tripwire manifest.** Every active workstream is listed here with its branch, PR,
> and protective tag. If a branch ever disappears from origin, this file still names
> it and its PR/tag — making the loss obvious and recovery trivial. Keep it current:
> add a row when a workstream branch is pushed; update status on merge.

**Last updated:** 2026-06-03

| WS | Title | Branch | PR | Protective tag | Status |
|----|-------|--------|----|----------------|--------|
| A | Transport abstraction (Ollama `/api/chat` + OpenAI-compat) | merged (squash #87) | [#87](https://github.com/scottblydotcom/hermia/pull/87) | `ws-a-reviewed-2026-06-03`, `ws-a-merged-2026-06-03` | ✅ Merged to `dev` — recovered after origin-branch loss; 8 findings + 2 Gemini guards fixed; all gates green |
| — | Recovery copy of A (pristine, do not edit) | `recover/workstream-a-transport` | — | `ws-a-reviewed-2026-06-03` | 🟢 Safety net — retain until A is confirmed stable on `dev` |
| B | hermia-agent sidecar (Windows Go GPU gaming-gate) | merged | [#85](https://github.com/scottblydotcom/hermia/pull/85), [#86](https://github.com/scottblydotcom/hermia/pull/86) | — | ✅ Done — verified through to physical machine (ScottWin11 .20) |
| C | Concurrent fleet runner (ThreadPoolExecutor, VRAM-aware) | `feat/workstream-c-concurrent-runner` | [#93](https://github.com/scottblydotcom/hermia/pull/93) | — | 🔵 In review — `_ps_cache` + `append_result` thread-safe; `run_fleet` concurrent via `ThreadPoolExecutor`; `--max-concurrency N` flag; VRAM-safe host grouping; all 852 tests green |
| D | Submission API + partial Sink | _planned_ | — | — | ⚪ Planned — independent of A |
| E | Deterministic multi-turn | _planned_ | — | — | ⚪ Planned — depends on A (message-list) |
| F | Test quality + framework coverage | `feat/workstream-f-test-quality` | [#94](https://github.com/scottblydotcom/hermia/pull/94) | — | 🔵 In review — corpus health, schema contract (totality + pos/neg table), framework taxonomy validation, CLI subprocess smoke; 1117 tests green |

## Rules

1. **A workstream branch gets a row here the moment it is pushed.**
2. **Open a draft PR immediately on first push** — a PR retains its head commits even
   if the branch is later deleted (the control that would have prevented the A loss).
3. **Tag reviewed milestones** (`ws-<x>-reviewed-<date>`) — annotated tags are not
   pruned and survive branch deletion.
4. **Never delete a branch until its PR reads "Merged"** (not merely "Closed").
5. Status legend: ⚪ planned · 🔵 in progress / review · ✅ merged · 🟢 protective copy.
