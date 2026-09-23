# hermia-bjlb — split every verdict by the test wording it answered

**Bead:** `hermia-bjlb` (*every security test has 2-3 prompt versions pooled under one test
id in the corpus; the report grades all of them with the current grader*)
**Branch:** `feature/hermia-bjlb-test-generation-report`, stacked on
`feature/hermia-au9l-not-evaluable-classes`, which is off `dev` @ `7477d93`.

## Why

17 of the 18 security tests have been reworded at least once and three of them twice, so a
rate computed per test id pools answers to different questions. The report now splits all
three verdict states by which wording each row answered, and keeps every individual wording
separate alongside it.

## The numbers, measured over `results/*.jsonl`

| wording | rows | resisted | compromised | not judged |
|---|---:|---:|---:|---:|
| shipping today | 13,326 | 84.8% | 5.4% | 9.7% |
| an older wording | 6,496 | 76.1% | 7.4% | 16.5% |
| prompt never stored | 156 | undefined | undefined | undefined |
| **pooled, as published** | **19,978** | **81.3%** | **6.0%** | **12.6%** |

The headline is unchanged and was re-verified against `dev` after every commit by running
the same command on both trees and diffing. 50 distinct scenarios are reported individually.

## What it makes visible

`instruction-override-resistance` scores **54.0% / 67.5% / 58.0%** resisted across its three
wordings, so the pooled figure describes none of them. `classification-routing`'s May wording
is the same device event with **no injection at all**, an accidental control group, and all
292 of its rows are correctly undefined under the current grader rather than counted as
failures.

## Guarantees

- The generations **partition** the corpus. Row counts sum to the total, and each one's
  states sum to its own rows, including a count for a verdict the module cannot read.
- Every per-generation rate keeps unevaluable rows in **its own** denominator.
- A wording that produced no verdict reports an **undefined** rate, in every column.
- The split is **by content, never by date**.

## Release labels are not test generations

17 of 18 current wordings first ran 2026-06-12 and the last on 2026-06-28. **v0.2.0 shipped
2026-07-06**, so v0.1.3 and v0.2.0 ran identical tests and the real boundary sits inside the
0.1.x era. A third of the corpus carries no release label at all.

## A cross-release comparison was built and retracted

On the 10 models common to all three releases, one model supplies 73% of the newest batch's
rows against 12% of the older two. Even that out and the compromise rate is flat (2.6 / 2.9 /
2.9) and the whole spread is runs that never came back, which is machine reliability rather
than model behaviour. **Do not publish a release-to-release security trend from this corpus.**

## What the review gates found

A four-lens adversarial panel (16 of 18 findings survived refutation) and five Antigravity
passes. Every blocker was the same defect wearing different clothes: **a name asserting a
cause the data did not support.**

- The wording table **vanished** when nothing could be compared, making a broken run
  byte-identical to a healthy one on 43 of 102 single-file invocations, and destroying a real
  wording split on 7 of them.
- The per-scenario generation label was **last-write-wins**, so it could be false for rows in
  its own block and flipped on input order alone.
- A record with no wording field was called `unrecorded`, which asserts the prompt was never
  stored, while a `prompt_version` sat in the same record contradicting it.
- The TUI stores failure text **as** the response body, so a timed-out request was named
  "a body was stored and is not valid JSON".
- A fix that filled an empty cell with a tautological "100% unjudged" was reverted: a
  proportion of a population where nothing was measured reads as a measurement, which this
  repo had already ruled out three times.

## Out of scope

Stamping a prompt hash on rows at write time. This reads what is already stored, so it works
on the whole historical corpus rather than only on runs made after a change.
