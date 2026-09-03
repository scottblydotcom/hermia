#!/usr/bin/env python3
"""WITNESS ratchet: the raw-coverage allowlist may only shrink.

pytest cannot enforce this. The suite runs statelessly against one commit, so a pull
request can add an allowlist entry and relax the assertion in the same diff and stay
green. This compares the allowlist in the working tree against the same constant on a
base ref, and fails when entries have been ADDED.

The allowlist is read by parsing the AST, never by importing or executing the base
revision's test file.

    python3 scripts/witness_allowlist_ratchet.py [--base origin/main]

Exit 0 = allowlist shrank or held. Exit 1 = entries added, or the constant went missing.

See docs/superpowers/specs/2026-08-31-witness-grader-completeness.md
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

CONST = "WITNESS_RAW_COVERAGE_ALLOWLIST"
TARGET = "tests/unit/test_schemas.py"
_CONSTRUCTORS = frozenset({"frozenset", "set"})


def extract(source: str, origin: str) -> set[str] | None:
    """Pull the allowlist's string literals out of `source` without executing it.

    Returns None when the constant is absent, which the caller distinguishes: absent on
    the BASE is the bootstrap case (this is the change introducing it); absent on HEAD
    means it was deleted or renamed, which must fail.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - malformed base is a real failure
        raise SystemExit(f"FAIL: could not parse {origin}: {exc}") from exc

    shadowed = _CONSTRUCTORS & _module_scope_bindings(tree)

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == CONST for t in targets):
            continue
        if node.value is None:
            break
        return _literal_strings(node.value, origin, shadowed)

    return None


def _module_scope_bindings(tree: ast.Module) -> set[str]:
    """Every name bound at MODULE scope, not descending into function or class bodies.

    Module scope is the only scope that matters here. The allowlist assignment is evaluated
    there, so only a module-level rebinding of `frozenset`/`set` can change what the call
    actually returns at runtime. A name bound inside a function body cannot, and refusing on
    those would reject ordinary test code that uses `set` as a local variable.
    """
    bound: set[str] = set()
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)  # the definition binds a module-scope name
            continue              # ...but its body is a different scope
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        stack.extend(ast.iter_child_nodes(node))
    return bound


def _literal_strings(value: ast.expr, origin: str, shadowed: frozenset[str] | set[str]) -> set[str]:
    """Resolve a literal set/frozenset of string constants, or refuse.

    ⚠️ THIS MUST REFUSE ANYTHING IT CANNOT SEE. An earlier version collected whatever
    string constants it found by walking the value and returned whatever that produced —
    including the EMPTY SET when the value was an alias like
    `WITNESS_RAW_COVERAGE_ALLOWLIST = ALLOWLIST`.

    That was an exploitable bypass, proven before this fix: move the real list into
    another module, import it, add an entry. The ratchet extracted {} from HEAD, compared
    it to the base, reported a shrinkage that never happened, and PASSED — while the
    runtime allowlist grew. Worse, it was self-perpetuating: once merged, every later
    change would extract {} on both sides and the ratchet would never fire again.

    An indirection is not an empty allowlist. It is an allowlist this script cannot read,
    and the only safe response is to stop. Found by outside-family review of PR #167.

    ⚠️ SECOND BYPASS, same shape, found by the next outside-family review of the same PR:
    `frozenset` and `set` are ordinary names, not syntax, so the target module can rebind
    them. With `def frozenset(x): return set(x) | {"sneaky"}` at module scope, this script
    reads the literal argument and sees one entry while Python computes two. Reproduced: the
    ratchet exited 0 reporting no additions while the runtime allowlist had grown.

    That defeats this script's whole reason to exist. The stateless pytest check
    (test_witness_allowlist_is_defined_readably) does catch the shadowing on its own — but
    the ratchet exists precisely because a pull request can neutralise a pytest check and
    add an entry in the SAME diff, which is exactly the two-step this permitted.

    `shadowed` therefore carries any module-scope rebinding of those constructors, and a
    call to a shadowed name is refused rather than read.
    """
    inner: list[ast.expr] | None = None

    if isinstance(value, ast.Set):                      # {"a", "b"}
        inner = list(value.elts)
    elif isinstance(value, ast.Call):                   # frozenset({...}) / frozenset([...])
        func = value.func
        if isinstance(func, ast.Name) and func.id in shadowed:
            raise SystemExit(
                f"FAIL: {CONST} in {origin} is built by calling {func.id!r}, but {func.id!r} "
                "is rebound at module scope in that file, so it is not the builtin. This "
                "script would read the literal argument while Python computes something "
                "else — the ratchet would pass while the allowlist grew. Remove the "
                "rebinding, or define the allowlist as a plain literal."
            )
        if isinstance(func, ast.Name) and func.id in _CONSTRUCTORS:
            if not value.args:
                inner = []                              # frozenset() — genuinely empty
            elif len(value.args) == 1 and isinstance(value.args[0], (ast.Set, ast.List, ast.Tuple)):
                inner = list(value.args[0].elts)

    if inner is None:
        raise SystemExit(
            f"FAIL: {CONST} in {origin} is not a literal set of strings, so this script "
            "cannot read it statically. That is not an empty allowlist — it is an "
            "unreadable one, and passing here would silently disable the ratchet forever. "
            "Define it inline as a literal frozenset({...}) of string constants, or update "
            "this script deliberately in the same change."
        )

    out: set[str] = set()
    for element in inner:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            raise SystemExit(
                f"FAIL: {CONST} in {origin} contains a non-literal entry "
                f"({type(element).__name__}). Every entry must be a plain string constant "
                "so the ratchet can compare it against the base ref."
            )
        out.add(element.value)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main", help="base ref to compare against")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    head_src = (repo / TARGET).read_text(encoding="utf-8")

    try:
        base_src = subprocess.run(
            ["git", "show", f"{args.base}:{TARGET}"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: could not read {TARGET} at {args.base}: {exc.stderr.strip()}")
        print("If the base ref is unavailable the ratchet has NOT run — this is not a pass.")
        return 1

    head = extract(head_src, "working tree")
    base = extract(base_src, args.base)

    if head is None:
        print(f"FAIL: {CONST} is missing from {TARGET} in the working tree.")
        print(
            "The ratchet cannot verify an allowlist that was deleted or renamed. If that "
            "was deliberate, update this script in the same change — do not leave a "
            "ratchet pointing at a constant that no longer exists."
        )
        return 1

    if base is None:
        print(f"BOOTSTRAP: {CONST} does not exist at {args.base}.")
        print(f"This is the change that introduces it, with {len(head)} entr"
              f"{'y' if len(head) == 1 else 'ies'}:")
        for h in sorted(head):
            print(f"  {h}")
        print("Nothing to ratchet against yet. Subsequent changes are compared to this.")
        return 0

    added = sorted(head - base)
    removed = sorted(base - head)

    print(f"base ({args.base}): {len(base)} entr{'y' if len(base) == 1 else 'ies'}")
    print(f"head:              {len(head)} entr{'y' if len(head) == 1 else 'ies'}")
    for r in removed:
        print(f"  removed (good):  {r}")

    if added:
        print()
        print("FAIL: the WITNESS raw-coverage allowlist may only shrink.")
        for a in added:
            print(f"  ADDED: {a}")
        print()
        print(
            "Each entry is a security test on which a compromise cannot be detected. "
            "Adding one widens a declared blind spot. If that is genuinely intended, it "
            "needs an explicit decision recorded on the pull request — not a silent line."
        )
        return 1

    print("OK: allowlist shrank or held.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
