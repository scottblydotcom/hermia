#!/usr/bin/env python3
"""Decompose the pre/post-GUARDS result shift into grader effect vs prompt effect.

  A = pre-GUARDS  responses, OLD grader  (recorded verdict)
  B = pre-GUARDS  responses, NEW grader  (re-graded)
  C = post-GUARDS responses, NEW grader  (re-graded)

  grader effect = B - A   (same responses, different yardstick)
  GUARDS effect = C - B   (same yardstick, different prompts)

C - B is computed ONLY over the (model, test_id) pairs present on BOTH sides,
so it is not contaminated by a changed model mix.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

SP = Path("/private/tmp/claude-501/-Users-scottbly-Git-hermia/8227e715-a5ca-4794-8900-ddb7d0290fe8/scratchpad")


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.open() if l.strip()]


pre = load(SP / "pre" / "regraded.jsonl")
post = load(SP / "post" / "regraded.jsonl")


def rate(rows, field):
    if not rows:
        return None
    return 100.0 * sum(bool(r[field]) for r in rows) / len(rows)


print("=" * 78)
print("HEADLINE (all rows, unmatched)")
print("=" * 78)
print(f"  pre-GUARDS  n={len(pre):>6}   A (old grader) = {rate(pre,'old_schema_compliant'):5.2f}%"
      f"   B (new grader) = {rate(pre,'new_schema_compliant'):5.2f}%")
print(f"  post-GUARDS n={len(post):>6}   A (old grader) = {rate(post,'old_schema_compliant'):5.2f}%"
      f"   C (new grader) = {rate(post,'new_schema_compliant'):5.2f}%")
print()
print(f"  GRADER EFFECT on pre-GUARDS data (B - A): "
      f"{rate(pre,'new_schema_compliant') - rate(pre,'old_schema_compliant'):+.2f} pp")
print(f"  naive pre→post shift, new grader (C - B): "
      f"{rate(post,'new_schema_compliant') - rate(pre,'new_schema_compliant'):+.2f} pp  <-- CONFOUNDED by model mix")

# ---- flip direction ----
f2p = sum(1 for r in pre if not r["old_schema_compliant"] and r["new_schema_compliant"])
p2f = sum(1 for r in pre if r["old_schema_compliant"] and not r["new_schema_compliant"])
print()
print(f"  pre-GUARDS flips under the new grader:  fail->pass = {f2p}   pass->fail = {p2f}")
print(f"  => new grader is {'STRICTER' if p2f > f2p else 'LOOSER' if f2p > p2f else 'NEUTRAL'}"
      f" on pre-GUARDS responses")

# ---- matched (model, test_id) ----
print()
print("=" * 78)
print("MATCHED on (model, test_id) — the defensible comparison")
print("=" * 78)

pre_by = defaultdict(list)
post_by = defaultdict(list)
for r in pre:
    pre_by[(r["model"], r["test_id"])].append(r)
for r in post:
    post_by[(r["model"], r["test_id"])].append(r)

common = sorted(set(pre_by) & set(post_by))
print(f"  pre pairs={len(pre_by)}  post pairs={len(post_by)}  COMMON={len(common)}")

if not common:
    print("  !! no overlap — cannot compute a matched GUARDS effect")
else:
    pre_m = [r for k in common for r in pre_by[k]]
    post_m = [r for k in common for r in post_by[k]]
    b = rate(pre_m, "new_schema_compliant")
    c = rate(post_m, "new_schema_compliant")
    a = rate(pre_m, "old_schema_compliant")
    print(f"  matched rows: pre n={len(pre_m)}, post n={len(post_m)}")
    print(f"    A  pre-GUARDS  / old grader = {a:5.2f}%")
    print(f"    B  pre-GUARDS  / NEW grader = {b:5.2f}%")
    print(f"    C  post-GUARDS / NEW grader = {c:5.2f}%")
    print()
    print(f"    grader effect (B-A) = {b-a:+.2f} pp")
    print(f"    GUARDS effect (C-B) = {c-b:+.2f} pp   <-- same grader, same models, same tests")

    # per-dimension
    print()
    print("  By dimension (matched):")
    dims = sorted({r["dimension"] for r in pre_m if r.get("dimension")})
    for d in dims:
        pm = [r for r in pre_m if r.get("dimension") == d]
        cm = [r for r in post_m if r.get("dimension") == d]
        if pm and cm:
            print(f"    {d:<14} B={rate(pm,'new_schema_compliant'):5.1f}%  "
                  f"C={rate(cm,'new_schema_compliant'):5.1f}%  "
                  f"delta={rate(cm,'new_schema_compliant')-rate(pm,'new_schema_compliant'):+6.2f} pp"
                  f"   (n_pre={len(pm)}, n_post={len(cm)})")

# ---- did the prompts actually change? ----
print()
print("=" * 78)
print("PROMPT-CHANGE PROOF (system-prompt hash per test_id)")
print("=" * 78)
pre_h = defaultdict(set)
post_h = defaultdict(set)
for r in pre:
    if r.get("system_prompt_sha12"):
        pre_h[r["test_id"]].add(r["system_prompt_sha12"])
for r in post:
    if r.get("system_prompt_sha12"):
        post_h[r["test_id"]].add(r["system_prompt_sha12"])

shared = sorted(set(pre_h) & set(post_h))
changed = [t for t in shared if pre_h[t] != post_h[t]]
same = [t for t in shared if pre_h[t] == post_h[t]]
print(f"  tests present both sides: {len(shared)}")
print(f"    system prompt CHANGED: {len(changed)}")
print(f"    system prompt IDENTICAL: {len(same)}")
if same:
    print(f"    unchanged tests: {', '.join(same[:12])}")
