# Reproducibility / Self-Divergence Floor — Design

**Date:** 2026-06-15
**Status:** Draft — ready for writing-plans
**Scope:** v0.2.0 scope item #2 (follows the merged determinism slice, PR #113)
**Parent spec:** `docs/superpowers/specs/2026-06-14-stack-fingerprint-design.md` (Round-2 §B defines the `reproducibility` block; §C the divergence ladder; §G the MVP confound controls)
**Related memory:** [[project_hermia_determinism_finding]], [[project_hermia_stack_fingerprint]], [[project_hermia_data_accounting]], [[backlog_qwen3_8b_anomaly]]

---

## Terminology (used throughout)

The word **cell** from the parent spec is retired here in favor of two precise terms:

- **trial** — one execution: one prompt delivered, one response received, one grade computed. **One trial = one JSONL result row.** (Analogous to a request/response "packet pair" in API-security tooling.)
- **trial group** — all trials sharing the same `(model, test)` identity on one host. Running `--repeat N` produces one trial group of N trials per `(model, test)`. The trial group is the unit over which reproducibility is measured.

(Across hosts, the full grouping identity is `(host/stack, model, test)`; within a single host's eval loop — where this work lives — `host` is fixed, so the group key is `(model, test)`.)

---

## Problem

The eval is now sampling-deterministic (`temperature=0.0`, `seed=42`, pinned and immutable — PR #113). But determinism is **necessary, not sufficient**: at `temp=0`, residual run-to-run nondeterminism can still flip outputs, driven by server-side batch-variant FP-reduction order (Thinking Machines), not RNG. Before Hermia can make any **cross-stack** divergence claim, it must first characterize **intra-group self-divergence** — how much a single fixed stack disagrees with itself across identical re-runs.

This is the noise floor. A cross-stack difference is only real if it exceeds this floor. Today Hermia measures nothing of the sort.

## Goal

Add a per-trial-group `reproducibility` block to every result row, computed over the N repeats already produced by `--repeat`. The block answers: **"When this (model, stack, test) is run N identical times, how consistently does it produce the same output, and how reliably does it pass?"**

Acceptance bar (from parent §B, ChatGPT side of the resolved split): **within-stack variance << between-stack variance** — NOT hard-zero. Residual batch/FP nondeterminism makes a hard-0 floor unattainable on real GPUs, so a relative bar is used. This spec ships the *measurement*; the A/B proof that the bar holds is scope item #5 (MVP experiment).

## Non-goals

- **Semantic / functional equivalence** (a real but out-of-scope third rung). `8`, `7+1`, `4+4`, `2×2×2` are "the same answer" to a human but differ at both byte and JSON-canonical levels. Detecting this requires a per-test equivalence function or LLM-as-judge — expensive and test-specific. Our current corpus grades structured JSON, where schema-canonical equality already captures functional sameness, so this rung does not bite yet. It belongs in the divergence-ladder work (parent §C) as a future rung between `canonical_json_equal` and a human judge, not here. **Recorded so it is not silently forgotten.**
- **Latency / performance reproducibility.** Reproducibility of *output* is this item. Reproducibility of *timing* is a separate correctness-vs-performance concern (parent spec splits these sub-trees deliberately) and is not added here.
- **Per-test or per-host N.** N is the existing global `--repeat` flag (see Decision 4).
- **Cross-stack comparison / the A/B proof.** That is scope item #5; this item only establishes the per-group measurement it will consume.

---

## Design decisions (background + trade-offs)

### Decision 1 — Extend the existing repeat loop, do not build a parallel subsystem

`fleet.py:_run_host_eval` already runs N repeats per `(model, test)`, accumulates them into `run_results: list[dict]`, calls `score_rows(run_results)`, and stamps the robustness aggregates on every row before writing (lines 213–237). Reproducibility is conceptually *one more aggregate over the same list*. We add a second function call into that same loop.

- **Trade-off:** Every eval run now produces reproducibility data for free (not opt-in). Upside: anyone running `--repeat 10` gets the determinism signal automatically. Cost: the metric becomes part of the **output-schema contract** — downstream consumers (Grafana, submission API, `hermia-analyze`, TUI) will expect the field, so we own its correctness, shape-stability, and performance from here forward. Accepted: the loop already does the expensive work (the N model calls); the aggregate is microseconds on top.

### Decision 2 — Denormalize the group summary onto every trial row

The `reproducibility` block is a property of the **trial group**, but it is stamped identically onto **every trial row** in that group (mirroring how `consistency_pct`/`pass_count`/`robustness_n` already work).

Concretely — 10 repeats of `(qwen3:8b, tool-calling)` produce 10 JSONL rows; each keeps its **own** `raw_response`/`elapsed_sec`/`tokens`, and each **also** carries a copy of the same `reproducibility` summary.

- **Trade-off vs. emitting one summary row per group:** the per-group-summary layout would write fewer rows but **discard the individual `raw_response` strings** — which are the *evidence* for the reported rates. Denormalizing costs redundant storage (the summary repeats N times) but keeps every row self-describing and preserves the raw outputs a reviewer needs to verify the number. For an audit-grade research tool whose consumers read flat JSONL (no join/aggregation step), this is the correct trade: **schema follows the queries you expect to run** ("show me a row / rows matching X"), not normalization theory.

### Decision 3 — Same dict reference on every row in a group (safe here)

`row["reproducibility"] = repro` assigns the *same* dict object to every row in the group. This is safe because the next operation is `append_result(...)`, which JSON-serializes each row (a deep copy to disk); nothing mutates the dict between assignment and serialization. The loop is small enough that the safety is obvious from reading it. (A defensive `dict(repro)` copy would be visually-obvious-correct at zero real cost; the plan may choose it for reader-friendliness — optimize for the reader.)

### Decision 4 — N is the existing `--repeat` flag

No per-test annotation, no per-host YAML field. The parent spec calls for N=10–20 to characterize the floor; `--repeat 15` already does that. YAGNI: adding per-test/per-host N buys flexibility we do not need and a config surface we would have to test, document, and explain. If reality later forces per-test N, refactor then — carrying unused flexibility forward is the more common, costlier mistake.

### Decision 5 — Errored trials: honest "both" via an explicit valid-count

Some trials produce no output (90s TIMEOUT, EMPTY_RESPONSE, transport error); their `raw_response` is `""`. The poison case: if **all** N trials error, all empty strings match each other → a naive exact-match returns **1.0 ("perfectly reproducible")** about a model that produced nothing N times. That number can never be published.

Resolution (consistent with parent §G "drop TIMEOUT/EMPTY_RESPONSE from exact-match; report timeout rate separately"):

- **Exact-match rates** (`raw`, `canonical`) are computed **only over valid trials** (those that produced output). If `n_valid == 0`, both are `null` ("not measurable") — never 1.0, never 0.0.
- **Pass rate** is computed over **all N trials** — a timeout *is* an end-to-end failure from the user's standpoint and must count against it.
- **`n_valid`** is recorded so the error count (`n_repeats − n_valid`) is explicit and the reader can reconstruct any blended view.

This represents *both* realities the user asked for without a degenerate number: "when it answered, how consistent was it?" (exact-match over valid) and "how often did the whole thing work?" (pass-rate over all). The per-trial `failure_reason` and `raw_response` remain on every row regardless — the summary is a convenience, never the only copy of the truth.

A precomputed end-to-end "overall identical-output rate" was considered and rejected as redundant: `n_valid` + the two rates let any consumer derive it, and every extra precomputed field is one more thing to keep correct. Add it later only if practice demands it.

---

## Schema

A single `reproducibility` object on each result row:

```python
reproducibility: {
    "n_repeats": int,                            # total trials attempted in the group
    "n_valid": int,                              # trials that produced output (n_repeats − errored)
    "exact_match_rate_raw": float | None,        # P(trial.raw_response == modal raw_response),
                                                 #   over VALID trials only; null if n_valid == 0
    "exact_match_rate_canonical": float | None,  # same, over canonicalized output; null if n_valid == 0
    "pass_rate_mean": float,                     # mean(passed) over ALL n_repeats (timeout = fail)
    "pass_rate_stddev": float,                   # population stddev of pass outcomes over ALL n_repeats
}
```

Field semantics:

- **`n_repeats`** — lets consumers weight/filter by sample size (a rate at N=2 is not a rate at N=20).
- **`n_valid`** — the valid-trial denominator for the exact-match rates; `n_repeats − n_valid` is the error count.
- **`exact_match_rate_raw`** — fraction of valid trials whose byte-exact `raw_response` equals the **modal** (most common) raw output in the group. `1.0` = token-level determinism (the industry's target); low = stochastic drift. Modal (not all-pairs) is chosen for O(N) cost and because it matches the intuition "what's the dominant output and how reliably is it produced?"
- **`exact_match_rate_canonical`** — same, but over the canonicalized output (strip markdown fences + whitespace — the *same transform the grader applies*). Measures "did the grader see identical input each time?" A high-canonical / low-raw split means meaning is stable but formatting drifts.
- **`pass_rate_mean`** — fraction of all N trials that passed (`schema_compliant and not failure_reason`). Distinct from the existing `consistency_pct`, which measures self-agreement (an all-fail group is 100% consistent); `pass_rate_mean` measures actual success.
- **`pass_rate_stddev`** — population stddev of the binary pass outcomes. For binary data this is `sqrt(p(1−p))` (a function of the mean, not independent information) but is standard hygiene next to a rate and costs nothing.

Deliberately excluded: an `is_reproducible` boolean (threshold is the consumer's value judgment — publish numbers, not verdicts); `unique_output_count` (derivable from raw rows); per-rank rates (analysis-tier, for item #5).

---

## Components / isolation

- **`robustness.py` — new `compute_reproducibility(run_results) -> ReproducibilityResult`.** Lives next to `score_rows` because `robustness.py` already *is* "turn N trial dicts into a summary"; reproducibility is one more such summary. Reuses the module's established dataclass + unit-test pattern. Returns a frozen `ReproducibilityResult` dataclass whose five+one field names match the schema verbatim, so `dataclasses.asdict(result)` yields the exact nested dict — type-safe and testable (`result.exact_match_rate_raw == 0.9`) without string-keying.
- **Canonicalization — shared, not duplicated.** The canonical exact-match MUST use the *same* transform the grader uses (`runner._strip_fences`, then strip) so `exact_match_rate_canonical` aligns with what the grader actually saw. Today neither `runner.py` nor `robustness.py` imports the other. To keep them in sync without a fragile `robustness → runner` dependency, extract `_strip_fences` into a small pure module (e.g. `hermia/normalize.py`, no deps) and import it from both. This is the one production refactor in scope — low-risk (move one pure function, update one import site in `runner.py`), justified by the new shared need (improve the code you're working in, don't bolt on a divergent copy).
- **`fleet.py:_run_host_eval` — one added call + one added stamp.** After the existing `score_rows` call: `repro = compute_reproducibility(run_results)`, then inside the per-row write loop `row["reproducibility"] = asdict(repro)`. No structural change to the loop.

Error classification (which trials are "valid"): a trial is **invalid** when it failed to produce output — `failure_reason` indicates TIMEOUT / EMPTY_RESPONSE / transport error, equivalently `raw_response == ""`. `compute_reproducibility` filters on this to form the valid set for exact-match while keeping all N for pass-rate. The exact predicate is finalized in the plan against the `failure_reason` vocabulary in `run_test`.

---

## Data flow

```
_run_host_eval, per (model, test) trial group:
    run_results = []
    for run_index in 1..repeat:
        run_results.append(run_test(...))            # one trial → one row

    rob   = score_rows(run_results)                  # existing
    repro = compute_reproducibility(run_results)     # NEW — aggregate over the same list
    for row in run_results:
        row["consistency_pct"], row["pass_count"], row["robustness_n"] = rob...   # existing
        row["reproducibility"] = asdict(repro)       # NEW — group summary on every trial row
        append_result(row, jsonl_path, csv_path)     # existing — serializes each row independently
```

---

## Testing

Unit (`tests/unit/test_robustness.py`, a new `compute_reproducibility` test section alongside the existing `score_rows` tests):

- All-identical valid trials → `exact_match_rate_raw == 1.0`, `n_valid == n_repeats`.
- All-different valid trials → low raw rate; canonical higher when only formatting differs (fence/whitespace-only delta → `canonical == 1.0`, `raw < 1.0`).
- Mixed pass/fail valid trials → `pass_rate_mean` over all N; `pass_rate_stddev` matches `sqrt(p(1−p))`.
- **All-errored group → exact-match rates are `null` (NOT 1.0), `n_valid == 0`, `pass_rate_mean == 0.0`.** (The poison-case guard.)
- Partial-error group → exact-match over valid only; `n_valid == n_repeats − errored`; pass-rate over all N.
- Single trial (`n_repeats == 1`) → degenerate-but-defined (rate 1.0 over the one valid trial; stddev 0.0).
- Empty input → zeroed/`null` result, mirroring `score_rows([])`.
- `dataclasses.asdict()` of the result equals the documented schema dict exactly (field-name contract test).

Integration (`tests/unit/test_fleet.py`, extending the new repeat-loop family already added):

- `--repeat N` stamps an identical `reproducibility` block on all N rows of a group; `n_repeats == N`.
- Two tests × repeat=2 → each group's `n_repeats == 2` (per-group, not global) — already covered structurally by `test_run_host_eval_aggregates_are_per_cell_not_global`; extend to assert the `reproducibility` block.

Canonicalization parity:

- `exact_match_rate_canonical` uses the same fence-stripping as the grader — a fenced-vs-unfenced pair of otherwise-identical JSON is canonical-equal. Asserted against `normalize._strip_fences` directly so the shared helper can't silently drift from the grader.

---

## Backward compatibility

Purely additive: one new `reproducibility` key on each row; no existing field changes. The 895 pre-determinism rows simply lack the key (a missing `reproducibility` is the schema marker for "measured before this slice"), consistent with the data-accounting backfill plan ([[project_hermia_data_accounting]]). The `_strip_fences` extraction is a behavior-preserving move (same function, new home).

## Out-of-scope follow-ups (recorded)

- Semantic/functional-equivalence rung in the divergence ladder (parent §C).
- The A/B cross-stack proof experiment that consumes this floor (scope item #5).
- Optional precomputed end-to-end "overall identical-output rate" field — add only if practice demands it.
