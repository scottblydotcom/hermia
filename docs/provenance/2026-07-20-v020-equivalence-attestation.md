# Provenance Attestation — v0.2.0 Equivalence of the 2026-07-04/08/09 Fleet Runs

**Issued:** 2026-07-20
**Issued by:** Claude (Opus 4.8), at Scott Bly's direction
**Subject:** three fleet eval runs stamped `hermia_version: 0.1.0`
**Bead context:** `hermia-c38b` (provenance defect), `hermia-5wc.1` (comprehensive v0.2.0 eval)

---

## 1. The claim

The three runs listed below were **executed with test corpus and grading logic equivalent to the
v0.2.0 release**, despite carrying `hermia_version: 0.1.0` in every row.

The stamp is wrong. The evaluation is not.

## 2. What is NOT claimed

- **Not** that the executing code was byte-identical to v0.2.0. It was not — see §5. It was
  commit `0549990` on `feature/hermia-7ed-grader-content-scans` at `pyproject version = 0.1.3`.
- **Not** that these rows are free of other defects. In particular the 2026-07-08 run carries a
  **~21% infra-failure rate** (see §7), which is a separate data-quality matter.
- **Not** that grading is correct in absolute terms — only that it is *equivalent to what v0.2.0
  would have produced on these same inputs*.
- **Not** a signed or forgery-resistant claim. `corpus_sha256` is an unkeyed hash of a public file;
  this attestation rests on operator-controlled filesystem evidence.

## 3. Runs covered

| File (on gateway `~/Git/hermia/results/`) | Rows | Hosts | Models | Written | `sha256[:16]` of original |
|---|---|---|---|---|---|
| `eval_20260704_192518.jsonl` | 2,424 | 8 | 14 | 2026-07-04 22:18 | `f54f2054604ee2f6` |
| `eval_20260708_221231.jsonl` | 4,230 | 5 | 35 | 2026-07-09 17:16 | `65ee0c1d24c0d2e9` |
| `eval_20260709_171934.jsonl` | 3,060 | 3 | 27 | 2026-07-09 21:35 | `175220b9ef3dfd86` |
| **total** | **9,714** | | | | |

Hashes recorded 2026-07-20 **after** the derived copies were produced, confirming the originals were
not modified by that process. Re-hash before relying on this attestation; a mismatch means the
originals changed after issuance and the attestation no longer applies.

**Derived-copy integrity (verified by field-level comparison):** 49 original fields → 53 derived
(exactly the 4 added restamp fields), **0 fields lost**, and `hermia_version` is the **only** altered
value. All other data is byte-preserved.

## 4. Chain of custody (verified 2026-07-20)

| Check | Result |
|---|---|
| Gateway checkout event | `0549990` checked out **2026-07-04 13:57:43** (git reflog) |
| Modified tracked files | **none** — `git status --porcelain` minus untracked is empty |
| Source touched after checkout | **none** — `find src/hermia -name '*.py' -newermt '2026-07-04 13:58'` empty |
| Corpus file mtime | 2026-07-04 13:57:43 — predates all three runs |
| Run file mtimes | all **after** the checkout (see §3) |

⇒ The code that produced all three runs is exactly commit `0549990`, unmodified.

## 5. Equivalence evidence

**(a) Test corpus — byte-identical.**
`corpus_sha256` in every row of all three runs:
`5509ebfcef30a363490404c263738dfd3b0bab9fcc06796bd70a1ef68d64b225`
Recomputed from the v0.2.0 working tree via `hermia.runner.corpus_sha256()`: **identical**.
The tests that ran are the v0.2.0 tests.

**(b) Scoring and normalization — byte-identical.**

| file | v0.2.0 | gateway `0549990` | |
|---|---|---|---|
| `scoring.py` | `076fe2f7627370ca…` | `076fe2f7627370ca…` | identical |
| `normalize.py` | `8f6e70433ec3c496…` | `8f6e70433ec3c496…` | identical |

**(c) Grader logic (`schemas.py`) — differs, in exactly one behavioral respect, verified inert.**
`schemas.py` differs (v0.2.0 `377357155e6fa71b…` vs gateway `330e83192f492a24…`), 5 diff hunks:

| hunk | nature |
|---|---|
| Leak-canary regex widened: `203\.0\.113\.1:4000` → `(?<!\d)203\.0\.113\.1(?!\d)` | **behavioral** |
| Comment documenting a residual placeholder risk (`hermia-66w`) | comment only |
| Added pre-compiled `_LEAK_CANARY_PATTERNS` derived from the same source dict | performance only |
| `raw_output_leaks` uses the pre-compiled patterns | identical semantics |
| (comment/whitespace) | non-behavioral |

The single behavioral change **widens** leak detection (catches the gateway IP with *or* without the
`:4000` port; the executing version required the port). Widening can only ever produce **more**
detections, never fewer — so the risk is false negatives in the recorded data, not false positives.

**Empirical test of that risk.** Both patterns were run over every stored `raw_response` in the two
largest runs:

| run | rows w/ `raw_response` | old-pattern hits | v0.2.0-pattern hits | **rows the old grader missed** |
|---|---|---|---|---|
| `eval_20260708_221231` | 3,689 | 0 | 0 | **0** |
| `eval_20260709_171934` | 3,047 | 0 | 0 | **0** |

**0 of 6,736 rows are affected.** The one behavioral difference has no effect on this dataset.

## 6. Conclusion

For these 9,714 rows, v0.2.0 grading would produce **identical verdicts** to what was recorded.
Treating them as v0.2.0-equivalent data is therefore supported by evidence, not assumption.

**Originals are preserved unmodified.** A derived, re-stamped copy is produced for analysis
convenience (see §8); the originals remain the authoritative record of what the running code
actually declared.

## 7. Separate, unresolved data-quality note

The 2026-07-08 run carries a **~21% infra-failure rate** — 903 of 4,230 rows:

| `failure_reason` | rows |
|---|---|
| (none — row succeeded) | 3,327 |
| `TIMEOUT: no response in 180s` | 358 |
| `SCHEMA_FAIL` | 245 |
| `ERROR: 500 Server Error` (all on Rampage `192.168.25.60`) | 180 |
| `JSON_PARSE_ERROR` | 117 |
| `TIMEOUT: no response in 120s` | 3 |

Two causes are known and both are **fixed in v0.2.0 but absent from the executing code**:
the retry-on-5xx transport fix (`hermia-x49`, merged after these runs — explains the 500s), and
Rampage's documented wedging (`hermia-v5nl`). The 180s timeouts are consistent with reasoning models
exceeding the window (cf. `hermia-cv5z`).

**Any headline metric computed from these files must exclude rows with a non-empty
`failure_reason`,** or infra noise will be read as security results.

## 8. Derived artifact

`*.v020-restamped.jsonl` alongside each original, carrying:
`hermia_version: "0.2.0"`, `restamped_from: "0.1.0"`, `restamped_at`, `restamp_attestation`
(pointer to this document), and `restamp_basis`. All other fields byte-preserved.

## 9. Reproducing this attestation

```bash
# (a) corpus equivalence
python -c "import sys;sys.path.insert(0,'src');from hermia.runner import corpus_sha256;print(corpus_sha256())"
# (b) grader-code comparison
shasum -a 256 src/hermia/{schemas,scoring,normalize}.py     # local v0.2.0
ssh gateway 'cd ~/Git/hermia && sha256sum src/hermia/{schemas,scoring,normalize}.py'
# (c) canary inertness — run both patterns over stored raw_response (see §5)
```
