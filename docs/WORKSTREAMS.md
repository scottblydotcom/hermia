# Hermia Workstreams — Active Branch Manifest

> **Tripwire manifest.** Every active workstream is listed here with its branch, PR,
> and protective tag. If a branch ever disappears from origin, this file still names
> it and its PR/tag — making the loss obvious and recovery trivial. Keep it current:
> add a row when a workstream branch is pushed; update status on merge.

**Last updated:** 2026-06-03

| WS | Title | Branch | PR | Protective tag | Status |
|----|-------|--------|----|----------------|--------|
| A | Transport abstraction (Ollama `/api/chat` + OpenAI-compat) | `feat/workstream-a-transport` | [#87](https://github.com/scottblydotcom/hermia/pull/87) | `ws-a-reviewed-2026-06-03` | 🔵 In review — recovered after origin-branch loss; rebased, 8 findings fixed, all gates green; awaiting merge |
| — | Recovery copy of A (pristine, do not edit) | `recover/workstream-a-transport` | — | `ws-a-reviewed-2026-06-03` | 🟢 Safety net — keep until A is merged |
| B | hermia-agent sidecar (Windows Go GPU gaming-gate) | merged | [#85](https://github.com/scottblydotcom/hermia/pull/85), [#86](https://github.com/scottblydotcom/hermia/pull/86) | — | ✅ Done — verified through to physical machine (ScottWin11 .20) |
| C | Concurrent fleet runner (ThreadPoolExecutor, VRAM-aware) | _planned_ | — | — | ⚪ Planned — depends on A |
| D | Submission API + partial Sink | _planned_ | — | — | ⚪ Planned — independent of A |
| E | Deterministic multi-turn | _planned_ | — | — | ⚪ Planned — depends on A (message-list) |
| F | Test quality + framework coverage | _planned_ | — | — | ⚪ Planned — independent of A |

## Rules

1. **A workstream branch gets a row here the moment it is pushed.**
2. **Open a draft PR immediately on first push** — a PR retains its head commits even
   if the branch is later deleted (the control that would have prevented the A loss).
3. **Tag reviewed milestones** (`ws-<x>-reviewed-<date>`) — annotated tags are not
   pruned and survive branch deletion.
4. **Never delete a branch until its PR reads "Merged"** (not merely "Closed").
5. Status legend: ⚪ planned · 🔵 in progress / review · ✅ merged · 🟢 protective copy.
