#!/usr/bin/env python3
"""Reconstruct true corpus/grader provenance for every hermia run.

Version stamps are unreliable (absent before ~2026-06-12, mis-stamped in July).
Git history IS reliable. And crucially, every run row stores `raw_system` — the
system prompt actually sent — so a run's corpus version can be identified from
EVIDENCE (prompt-hash match against the corpus as it existed at each commit)
rather than from a date guess.

Emits JSON consumed by the spreadsheet builder.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/Users/scottbly/Git/hermia")
CORPUS = "src/hermia/test-datasets/agentic-tasks.json"
OUT = Path("/private/tmp/claude-501/-Users-scottbly-Git-hermia/8227e715-a5ca-4794-8900-ddb7d0290fe8/scratchpad/reconstruction.json")


def sh(*args) -> str:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, check=False).stdout


def h12(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- git history
def git_history(path: str, follow: bool = True) -> list[dict]:
    args = ["git", "log", "--format=%H|%ad|%an|%s", "--date=iso-strict"]
    if follow:
        args.append("--follow")
    args += ["--", path]
    out = sh(*args)
    rows = []
    for line in out.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            rows.append({"sha": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return rows


corpus_commits = git_history(CORPUS)
grader_commits = git_history("src/hermia/schemas.py")
for _g in grader_commits:
    pass
normalize_commits = git_history("src/hermia/normalize.py")
guards_commits = git_history("docs/GUARDS.md")

# ------------------------------------------- corpus fingerprint at each commit
# The corpus file was renamed (test-datasets/ -> src/hermia/test-datasets/)
# between 2026-05-15 and 2026-06-03. Try every known historical path.
CORPUS_PATHS = [
    "src/hermia/test-datasets/agentic-tasks.json",
    "test-datasets/agentic-tasks.json",
    "hermia/test-datasets/agentic-tasks.json",
]


def corpus_blob_at(sha: str) -> tuple[str, str | None]:
    for p in CORPUS_PATHS:
        blob = sh("git", "show", f"{sha}:{p}")
        if blob.strip():
            return blob, p
    return "", None


corpus_versions = []
for c in corpus_commits:
    blob, used_path = corpus_blob_at(c["sha"])
    if not blob.strip():
        print(f"  !! could not resolve corpus at {c['sha'][:7]} ({c['date'][:10]})")
        continue
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        continue
    tests = data.get("agentic_test_cases", data if isinstance(data, list) else [])
    prompts = {}
    for t in tests:
        tid = t.get("id")
        sysp = t.get("system", "")
        if tid:
            prompts[tid] = h12(sysp)
    corpus_versions.append(
        {
            "sha": c["sha"],
            "short": c["sha"][:7],
            "date": c["date"],
            "subject": c["subject"],
            "n_tests": len(tests),
            "path_at_commit": used_path,
            "corpus_file_sha256": hashlib.sha256(blob.encode()).hexdigest(),
            "prompt_hashes": prompts,
            "security_tests": sum(1 for t in tests if t.get("dimension") == "security"),
        }
    )

# oldest-first for era numbering
corpus_versions.sort(key=lambda v: v["date"])
for i, v in enumerate(corpus_versions, 1):
    v["corpus_era"] = f"C{i:02d}"

# GUARDS landing = commit 067f141 ("GUARDS 6/6 for all 30 tests")
GUARDS_SHA = "067f141c9dad5f288ebd501677625bc951a34a60"  # pragma: allowlist secret (git SHA)
guards_date = next((v["date"] for v in corpus_versions if v["sha"] == GUARDS_SHA), None)
for v in corpus_versions:
    v["guards_state"] = (
        "GUARDS" if v["date"] >= guards_date else "pre-GUARDS"
    ) if guards_date else "unknown"

# ------------------------------------------------------- runs: observed truth
INFRA = ("TIMEOUT", "HTTP_", "CONNECTION", "NETWORK", "TRANSPORT", "ERROR")


def is_infra(r: str) -> bool:
    r = (r or "").upper()
    return any(r.startswith(p) for p in INFRA)


runs = []
for f in sorted((REPO / "results").glob("eval_2026*.jsonl")):
    if ".v020-restamped" in f.name:
        continue
    m = re.search(r"eval_(\d{8})_(\d{6})", f.name)
    if not m:
        continue
    date_s = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
    time_s = f"{m.group(2)[:2]}:{m.group(2)[2:4]}:{m.group(2)[4:6]}"

    observed: dict[str, set] = defaultdict(set)
    all_tids: set = set()
    n = 0
    infra = 0
    models: Counter = Counter()
    hosts: set = set()
    dims: Counter = Counter()
    ver = None
    corpus_stamp = None
    git_sha_stamp = None
    n_raw = 0
    passes = 0
    graded = 0

    with f.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            if ver is None:
                ver = row.get("hermia_version")
                corpus_stamp = row.get("corpus_sha256")
                git_sha_stamp = row.get("git_sha")
            models[row.get("model", "?")] += 1
            if row.get("test_id"):
                all_tids.add(row["test_id"])
            if row.get("host"):
                hosts.add(row["host"])
            if row.get("dimension"):
                dims[row["dimension"]] += 1
            if is_infra(row.get("failure_reason")):
                infra += 1
                continue
            sysp = row.get("raw_system")
            if sysp:
                n_raw += 1
                observed[row.get("test_id", "?")].add(h12(sysp))
            if row.get("raw_response"):
                graded += 1
                passes += int(bool(row.get("schema_compliant")))

    # --- identify corpus version by prompt-hash evidence ---
    best = None
    for v in corpus_versions:
        match = total = 0
        for tid, hs in observed.items():
            if tid in v["prompt_hashes"]:
                total += 1
                if v["prompt_hashes"][tid] in hs:
                    match += 1
        if total:
            score = match / total
            if best is None or score > best["score"] or (
                score == best["score"] and v["date"] > best["date"]
            ):
                best = {
                    "score": score,
                    "matched": match,
                    "compared": total,
                    "sha": v["sha"],
                    "short": v["short"],
                    "era": v["corpus_era"],
                    "date": v["date"],
                    "subject": v["subject"],
                    "guards_state": v["guards_state"],
                }

    # --- grader version inferred by date ordering (NOT fingerprinted) ---
    run_iso = f"{date_s}T{time_s}"
    g = next((c for c in grader_commits if c["date"][:19] <= run_iso), None)

    runs.append(
        {
            "file": f.name,
            "run_date": date_s,
            "run_time": time_s,
            "rows": n,
            "distinct_tests_run": len(all_tids),
            "infra_rows": infra,
            "gradeable_rows": graded,
            "recorded_pass_pct": round(100 * passes / graded, 2) if graded else None,
            "rows_with_raw_system": n_raw,
            "version_stamp": ver,
            "corpus_sha256_stamp": (corpus_stamp or "")[:12] or None,
            "git_sha_stamp": git_sha_stamp,
            "n_models": len(models),
            "n_hosts": len(hosts),
            "top_models": ", ".join(m for m, _ in models.most_common(4)),
            "dimensions": ", ".join(f"{d}:{c}" for d, c in dims.most_common()),
            "corpus_match_score": round(best["score"], 4) if best else None,
            "corpus_matched_tests": f"{best['matched']}/{best['compared']}" if best else None,
            "corpus_era": best["era"] if best else None,
            "corpus_commit": best["short"] if best else None,
            "corpus_commit_subject": best["subject"] if best else None,
            "guards_state": best["guards_state"] if best else None,
            "corpus_provenance": (
                "VERIFIED (prompt-hash)" if best and best["score"] >= 0.99
                else "PARTIAL (prompt-hash)" if best and best["score"] >= 0.5
                else "UNVERIFIED"
            ) if best else "NO raw_system",
            "grader_commit": g["sha"][:7] if g else None,
            "grader_commit_date": g["date"][:10] if g else None,
            "grader_commit_subject": g["subject"] if g else None,
            "grader_provenance": "INFERRED (date order)",
            "date_based_guards": ("GUARDS" if date_s >= (guards_date or "")[:10] else "pre-GUARDS"),
            "stale_checkout": bool(
                best and best["guards_state"] == "pre-GUARDS"
                and date_s >= (guards_date or "")[:10] and best["score"] >= 0.99
            ),
        }
    )

OUT.write_text(
    json.dumps(
        {
            "corpus_versions": corpus_versions,
            "corpus_commits": corpus_commits,
            "grader_commits": grader_commits,
            "normalize_commits": normalize_commits,
            "guards_commits": guards_commits,
            "runs": runs,
            "guards_landing_sha": GUARDS_SHA,
            "guards_landing_date": guards_date,
        },
        indent=2,
    )
)

print(f"corpus versions: {len(corpus_versions)}  (eras C01..{corpus_versions[-1]['corpus_era']})")
print(f"grader commits : {len(grader_commits)}")
print(f"runs analysed  : {len(runs)}")
print()
prov = Counter(r["corpus_provenance"] for r in runs)
for k, v in prov.most_common():
    print(f"  {k:<26} {v}")
print()
gs = Counter(r["guards_state"] for r in runs)
for k, v in gs.most_common():
    print(f"  guards_state={k}: {v}")
print(f"\nwrote {OUT}")
