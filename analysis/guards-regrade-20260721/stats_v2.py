#!/usr/bin/env python3
"""v2: classify runs by HASH-VERIFIED corpus era, not by run date.

Two runs (2026-06-23, 2026-06-24) postdate the GUARDS commit but used a stale
pre-GUARDS checkout (prompts match C12 at 28/28). Date-based bucketing put their
pre-GUARDS prompts in the post-GUARDS group, diluting the effect.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

SP = Path("/private/tmp/claude-501/-Users-scottbly-Git-hermia/8227e715-a5ca-4794-8900-ddb7d0290fe8/scratchpad")

D = json.load((SP / "reconstruction.json").open())
# authoritative map: file -> hash-verified GUARDS state
state = {r["file"]: r["guards_state"] for r in D["runs"]
         if r["corpus_provenance"].startswith("VERIFIED")}
excluded = [r["file"] for r in D["runs"] if not r["corpus_provenance"].startswith("VERIFIED")]


def load(p):
    return [json.loads(l) for l in p.open() if l.strip()]


rows = load(SP / "pre" / "regraded.jsonl") + load(SP / "post" / "regraded.jsonl")

pre, post, dropped = [], [], 0
for r in rows:
    s = state.get(r["source_file"])
    if s == "pre-GUARDS":
        pre.append(r)
    elif s == "GUARDS":
        post.append(r)
    else:
        dropped += 1

print(f"reclassified by hash-verified corpus era")
print(f"  pre-GUARDS rows : {len(pre)}")
print(f"  GUARDS rows     : {len(post)}")
print(f"  dropped (unverified provenance): {dropped}  files={excluded}")
print()


def rate(rows, f="new_schema_compliant"):
    return 100.0 * sum(bool(r[f]) for r in rows) / len(rows) if rows else None


def ztest(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se if se else 0.0
    pv = math.erfc(abs(z) / math.sqrt(2))
    sd = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return p1 * 100, p2 * 100, (p2 - p1) * 100, z, pv, (p2 - p1 - 1.96 * sd) * 100, (p2 - p1 + 1.96 * sd) * 100


def counts(rows, f="new_schema_compliant"):
    return sum(bool(r[f]) for r in rows), len(rows)


# grader effect on pre-GUARDS
f2p = sum(1 for r in pre if not r["old_schema_compliant"] and r["new_schema_compliant"])
p2f = sum(1 for r in pre if r["old_schema_compliant"] and not r["new_schema_compliant"])
print("=" * 80)
print("GRADER EFFECT (pre-GUARDS rows, hash-verified)")
print("=" * 80)
print(f"  A old grader = {rate(pre,'old_schema_compliant'):.2f}%   B new grader = {rate(pre):.2f}%"
      f"   delta = {rate(pre)-rate(pre,'old_schema_compliant'):+.2f} pp")
print(f"  flips: fail->pass = {f2p}   pass->fail = {p2f}   => "
      f"{'STRICTER' if p2f>f2p else 'LOOSER' if f2p>p2f else 'NEUTRAL'}")

# matched
pre_by, post_by = defaultdict(list), defaultdict(list)
for r in pre:
    pre_by[(r["model"], r["test_id"])].append(r)
for r in post:
    post_by[(r["model"], r["test_id"])].append(r)
common = set(pre_by) & set(post_by)
pre_m = [r for k in common for r in pre_by[k]]
post_m = [r for k in common for r in post_by[k]]

print()
print("=" * 80)
print("MATCHED on (model, test_id) — hash-verified eras")
print("=" * 80)
print(f"  common pairs = {len(common)}   pre n={len(pre_m)}  post n={len(post_m)}")
bx, bn = counts(pre_m)
cx, cn = counts(post_m)
p1, p2, d, z, pv, lo, hi = ztest(bx, bn, cx, cn)
print(f"    B pre  = {p1:.2f}%   C post = {p2:.2f}%")
print(f"    GUARDS effect = {d:+.2f} pp   95% CI [{lo:+.2f}, {hi:+.2f}]   z={z:.2f}   p={pv:.3g}")

print()
print("  SECURITY dimension:")
ps = [r for r in pre_m if r.get("dimension") == "security"]
cs = [r for r in post_m if r.get("dimension") == "security"]
bx, bn = counts(ps)
cx, cn = counts(cs)
p1, p2, d, z, pv, lo, hi = ztest(bx, bn, cx, cn)
print(f"    B = {p1:.2f}% ({bx}/{bn})   C = {p2:.2f}% ({cx}/{cn})")
print(f"    effect = {d:+.2f} pp   95% CI [{lo:+.2f}, {hi:+.2f}]   z={z:.2f}   p={pv:.3g}")

print()
print("  By dimension:")
for dim in sorted({r["dimension"] for r in pre_m if r.get("dimension")}):
    pm = [r for r in pre_m if r.get("dimension") == dim]
    cm = [r for r in post_m if r.get("dimension") == dim]
    if pm and cm:
        print(f"    {dim:<12} B={rate(pm):5.1f}%  C={rate(cm):5.1f}%  "
              f"delta={rate(cm)-rate(pm):+6.2f} pp  (n={len(pm)}/{len(cm)})")

print()
print("  Per-model (security, >=20 rows both sides):")
up = down = flat = 0
for m in sorted({r["model"] for r in ps} & {r["model"] for r in cs}):
    pm = [r for r in ps if r["model"] == m]
    cm = [r for r in cs if r["model"] == m]
    if len(pm) < 20 or len(cm) < 20:
        continue
    delta = rate(cm) - rate(pm)
    up += delta > 1
    down += delta < -1
    flat += -1 <= delta <= 1
print(f"    improved={up}  degraded={down}  flat={flat}")
