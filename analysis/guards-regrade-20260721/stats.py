#!/usr/bin/env python3
"""Significance + robustness checks on the matched GUARDS effect."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

SP = Path("/private/tmp/claude-501/-Users-scottbly-Git-hermia/8227e715-a5ca-4794-8900-ddb7d0290fe8/scratchpad")


def load(p):
    return [json.loads(l) for l in p.open() if l.strip()]


pre = load(SP / "pre" / "regraded.jsonl")
post = load(SP / "post" / "regraded.jsonl")

pre_by, post_by = defaultdict(list), defaultdict(list)
for r in pre:
    pre_by[(r["model"], r["test_id"])].append(r)
for r in post:
    post_by[(r["model"], r["test_id"])].append(r)
common = set(pre_by) & set(post_by)
pre_m = [r for k in common for r in pre_by[k]]
post_m = [r for k in common for r in post_by[k]]


def ztest(x1, n1, x2, n2):
    """Two-proportion z-test. Returns (p1, p2, diff_pp, z, p_value, ci_lo, ci_hi)."""
    p1, p2 = x1 / n1, x2 / n2
    pool = (x1 + x2) / (n1 + n2)
    se_pool = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pool if se_pool else 0.0
    # two-sided p via erfc
    pval = math.erfc(abs(z) / math.sqrt(2))
    se_diff = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    lo = (p2 - p1) - 1.96 * se_diff
    hi = (p2 - p1) + 1.96 * se_diff
    return p1 * 100, p2 * 100, (p2 - p1) * 100, z, pval, lo * 100, hi * 100


def counts(rows, field="new_schema_compliant"):
    return sum(bool(r[field]) for r in rows), len(rows)

print("=" * 84)
print("MATCHED GUARDS EFFECT — significance")
print("=" * 84)
b_x, b_n = counts(pre_m)
c_x, c_n = counts(post_m)
p1, p2, d, z, pv, lo, hi = ztest(b_x, b_n, c_x, c_n)
print(f"  B (pre/new grader)  = {p1:5.2f}%  ({b_x}/{b_n})")
print(f"  C (post/new grader) = {p2:5.2f}%  ({c_x}/{c_n})")
print(f"  diff = {d:+.2f} pp   95% CI [{lo:+.2f}, {hi:+.2f}]   z={z:.2f}   p={pv:.3g}")
print(f"  => {'SIGNIFICANT at p<0.05' if pv < 0.05 else 'NOT significant at p<0.05'}")

print()
print("=" * 84)
print("SECURITY DIMENSION ONLY (the claim that matters for GUARDS)")
print("=" * 84)
pre_s = [r for r in pre_m if r.get("dimension") == "security"]
post_s = [r for r in post_m if r.get("dimension") == "security"]
b_x, b_n = counts(pre_s)
c_x, c_n = counts(post_s)
p1, p2, d, z, pv, lo, hi = ztest(b_x, b_n, c_x, c_n)
print(f"  B = {p1:5.2f}%  ({b_x}/{b_n})")
print(f"  C = {p2:5.2f}%  ({c_x}/{c_n})")
print(f"  diff = {d:+.2f} pp   95% CI [{lo:+.2f}, {hi:+.2f}]   z={z:.2f}   p={pv:.3g}")
print(f"  => {'SIGNIFICANT at p<0.05' if pv < 0.05 else 'NOT significant at p<0.05'}")

print()
print("=" * 84)
print("PER-MODEL (security dim) — is the effect broad or driven by a few models?")
print("=" * 84)
models = sorted({r["model"] for r in pre_s} & {r["model"] for r in post_s})
up = down = flat = 0
for m in models:
    pm = [r for r in pre_s if r["model"] == m]
    cm = [r for r in post_s if r["model"] == m]
    if len(pm) < 20 or len(cm) < 20:
        continue
    bx, bn = counts(pm)
    cx, cn = counts(cm)
    delta = 100 * (cx / cn - bx / bn)
    mark = "UP  " if delta > 1 else ("DOWN" if delta < -1 else "flat")
    if delta > 1:
        up += 1
    elif delta < -1:
        down += 1
    else:
        flat += 1
    print(f"  {m:<34} B={100*bx/bn:5.1f}% (n={bn:<5}) C={100*cx/cn:5.1f}% (n={cn:<5}) "
          f"{delta:+6.2f} pp  {mark}")
print()
print(f"  models improved={up}  degraded={down}  flat={flat}   "
      f"(only models with >=20 rows both sides)")

print()
print("=" * 84)
print("HOST / BACKEND COVERAGE — what this comparison does NOT control for")
print("=" * 84)
pre_hosts = {r.get("host") for r in pre_m}
post_hosts = {r.get("host") for r in post_m}
print(f"  pre-GUARDS hosts  ({len(pre_hosts)}): {sorted(str(h) for h in pre_hosts)}")
print(f"  post-GUARDS hosts ({len(post_hosts)}): {sorted(str(h) for h in post_hosts)}")
print(f"  hosts on BOTH sides: {len(pre_hosts & post_hosts)}")
