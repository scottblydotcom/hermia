# hermia-au9l — break the not-evaluable bucket into its real classes

**Bead:** `hermia-au9l` (*canonical_security_report: break the not-evaluable bucket into its
real classes so an unattributable wrong route is visible, not pooled with timeouts*)
**Branch:** `feature/hermia-au9l-not-evaluable-classes` off `dev` @ `7477d93`
**Baseline:** `.venv/bin/pytest -q` → 2649 passed, 28 skipped, exit 0.

## The problem

`canonical_security_report` reports `not_evaluable` as one integer. Corpus-wide that is
2,526 rows and they are not one thing. For `classification-routing` it is 500 rows, and
410 of them are a model that routed to the attacker's demanded target and gave a reason
citing no authority — indistinguishable in the report from a host that timed out.

## Measured ground truth (103 files, `results/*.jsonl`, 19,978 distinct security rows)

Every number below was counted before any code was written, by a script that does not use
the new code. It is the acceptance target, not an estimate.

| verdict | rows |
|---|---|
| resisted | 16,250 |
| compromised | 1,202 |
| not_evaluable | 2,526 |

not_evaluable decomposes, exhaustively and disjointly, into:

| class | rows |
|---|---|
| no-body | 1,328 |
| unparsed | 681 |
| wrong-route-not-attributable | 410 |
| envelope-rejected | 107 |
| grader-error | 0 (has never fired on any corpus row) |

Sum = 2,526, equal to `not_evaluable`. Nothing leaves the denominator.

### The finding that changes the design

Hashing `raw_system + "\0" + raw_prompt` per row shows `classification-routing`'s 1,098
rows span **three distinct prompt versions**:

| version | rows | not-evaluable | matches the shipped test definition |
|---|---|---|---|
| `c23f8aef9be0` | 756 | 189 | **yes** |
| `0332fffa37ac` | 292 | 292 | no — May 2026, 297-char system prompt, contains no injection at all |
| `0f92f5e2cac7` | 50 | 19 | no — has the injection, older system prompt |

So the 410 "wrong route, no citable authority" rows split 271 / 123 / 16. **271 of them
answered a scenario that contained no injection and had no correct route to miss.**
Reporting 410 under that name would publish a number 3.3× the honest one and would
contradict the repo's own `catalog-meta/classification-routing.json`, which states 139.

The comparison against the shipped definition is mechanical: `agentic-tasks.json` ships all
30 cases with `system` and `prompt`, hashed the same way. It is not a keyword test — the
bead explicitly rules out keyword detection such as matching on "playbook".

### Provenance gaps that would make a naive version key lie

- `multiturn-boundary-persistence`: all 744 rows store `raw_turns` and **no** `raw_prompt`.
  A naive hash gives all 744 one identical key and reports "1 prompt version" falsely.
- 156 rows across 12 tests store neither `raw_system` nor `raw_prompt`.

Therefore the version key is `None` when either field is missing or blank, surfaced as
`"unknown"`, never as a hash of empty strings.

## What was built

Measured over `results/*.jsonl` after the change — these reproduce the reference numbers
computed before any code was written, to the digit:

| class | rows |
|---|---:|
| timeout | 747 |
| unparseable | 681 |
| transport-error | 408 |
| scenario-not-shipped | 337 |
| no-stored-body | 154 |
| routed-to-injection-target-uncited | 123 |
| checker-rejected | 57 |
| backend-error | 14 |
| empty-response | 5 |

Sum 2,526 = `not_evaluable`. Nine further classes are defined and fire on zero rows, so a
grader crash, an unrecorded prompt, a missing shipped definition, a retry exhaustion, an
API error, a body-less row carrying only a stored grade, a reasoning model that spent its
budget in the thinking channel, an unknown failure reason and a record from another
producer cannot be filed as something already understood.

The three-state verdicts are byte-identical to `dev` at `7477d93`: 16,250 / 1,202 / 2,526,
81.3% / 6.0% / 12.6%. Verified by running the same command on both and diffing.

## Four corrections the design panel forced, before any code was written

1. **The breakdown had to live in `summarize()`, not `canonical_security_report()`.**
   `main()` reaches its report through `_with_canonical_fields(summarize(...))` and never
   calls that function, so the first design would have printed no breakdown at all from the
   documented CLI invocation while every unit test passed.
2. **`wrong-route-not-attributable` was false for 271 of the 410 rows it would hold.** They
   answered the May-2026 prompt, which carries no injection and whose agent list has no
   `building-automation-agent` to route to. Split into `scenario-not-shipped` and
   `routed-to-injection-target-uncited`, on a content hash rather than a keyword.
3. **`no-body` named 1,328 rows after a condition true of 154 of them**, and duplicated the
   existing `not_rederivable` figure. Split into the four names `catalog-meta/_scoring.md`
   already publishes.
4. **The scenario key returned `None` for 744 rows with complete provenance.**
   `multiturn-boundary-persistence` ships `prompt: ""` and two `turns`; the blank prompt is
   the correct recorded value, not absent data.

## The defect only the corpus check caught

Reading `raw_turns` in preference to `raw_prompt` looked right and passed every unit test.
On the real corpus it put 517 rows in `scenario-not-shipped` and left both test-specific
classes empty, because the runner stores a rendered `raw_turns` on single-turn rows while
the shipped cases have no `turns` key. Prompt now wins when present; turns are the
fallback. Pinned by `test_a_single_turn_row_matches_the_shipped_prompt_despite_carrying_turns`.

## Out of scope

- No verdict moves. Nothing leaves `not_evaluable`; the bucket gets an internal breakdown.
- Generalising the scenario key across all 18 tests, and keying per-test rates by version,
  stays with `hermia-bjlb` (*every security test has 2-3 prompt versions pooled under one
  test id*). Flagged in the printed output and in `catalog-meta/_scoring.md`: **6,496 of
  the 19,978 security rows are off-version, including 481 of the 1,202 compromises.**
- `hermia-gofj` (*a few-shot-poisoning response carrying the poisoned `system_info` field
  fires no gate*) was filed from a sample taken here, and deliberately not fixed: it would
  create compromises, which this change must not do.

## What the review gates found, after the design panel

A five-lens adversarial panel and two Antigravity passes ran against the committed code.
Sixteen findings survived refutation out of twenty, plus five from Antigravity. The ones
that mattered shared a shape: **a class name asserting a cause that did not happen.**

- The shipped-version guard **failed open**. Reproduced end to end: with the packaged test
  definitions unreadable, 287 rows moved into `routed-to-injection-target-uncited` at exit
  0 with nothing on stderr, 271 of them answering a prompt with no injection in it. The
  guard originally written here only prevented the opposite error.
- The reason map knew **5 of the package's 12** failure tokens. `API_ERROR` and
  `RETRY_EXHAUSTED` are live runner paths that no corpus row carries, so no amount of
  measuring against the data could have found the gap — only iterating the vocabulary.
- `EMPTY_RESPONSE` was filed as a transport failure; the runner sets it only when the
  request succeeded.
- Two per-row crashes that would have abandoned the corpus from inside a helper: a lone
  surrogate in stored text, and unserialisable `raw_turns`.
- A mutation run during review misspelled three class names and **all 85 tests passed**.
  `NOT_EVALUABLE_CLASSES` was declared and enforced nowhere. Now pinned, with a positive
  control proving the mutation fails the test.

## Filed, not fixed

- `hermia-hv3p` — *`_STATUS_NOISE` strips digits, so a numbered agent like
  `security-agent-2` normalises to the injection target.* Pre-existing, from the hijack
  detector. Zero corpus rows affected. Fixing it could move a compromised verdict.
- `hermia-gofj` — *a few-shot-poisoning response carrying the poisoned `system_info` field
  fires no gate.* Fixing it would create compromises.
