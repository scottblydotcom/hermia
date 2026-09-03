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

# Builtins that can rewrite the module namespace without any visible binding. A test module
# has no business calling these at module scope, and each of them defeats static reading.
_DYNAMIC_BUILTINS = frozenset(
    {"globals", "locals", "vars", "exec", "eval", "setattr", "delattr", "__import__"}
)


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

    dynamic = _dynamic_constructs(tree)
    if dynamic:
        raise SystemExit(
            f"FAIL: {origin} uses {', '.join(sorted(dynamic))} at module scope. That can "
            f"rebind {CONST} with nothing for this script to read, so the allowlist it "
            "compares would not be the one Python uses. Module scope must stay statically "
            "readable; move dynamic code inside a function."
        )

    shadowed = _CONSTRUCTORS & _module_scope_bindings(tree)
    values, other = _const_bindings(tree)

    if other or len(values) > 1:
        raise SystemExit(
            f"FAIL: {CONST} in {origin} is bound {len(values) + other} times at module "
            "scope, or bound in a form this script cannot resolve. It must be assigned "
            "exactly once, as a plain literal. Python uses the LAST binding executed while "
            "this script would have to guess which one that is — and guessing wrong is how "
            "a ratchet passes while the allowlist grows."
        )

    if not values:
        return None
    return _literal_strings(values[0], origin, shadowed)


def _dynamic_constructs(tree: ast.Module) -> set[str]:
    """Module-scope constructs that can rebind a name with no binding node to find.

    ⚠️ BYPASSES 5 AND 6, and the reason this function exists at all rather than a seventh
    special case. Both were reproduced:

        WITNESS_RAW_COVERAGE_ALLOWLIST = frozenset({"a"})
        from elsewhere import *            # rebinds it; alias.name is "*", never the const

        WITNESS_RAW_COVERAGE_ALLOWLIST = frozenset({"a"})
        globals()["WITNESS_RAW_COVERAGE_ALLOWLIST"] = frozenset({"a", "sneaky"})
                                          # a Subscript store: neither a Name nor an Attribute

    Six bypasses of one shape have now been fixed here, and each fix was another guess at
    what the adversary might write next. Predicting a Python module's runtime value from its
    source is undecidable in general, so enumerating attacks cannot terminate.

    This inverts it. Rather than listing what is forbidden, the module must be STATICALLY
    BORING at module scope: no star imports, and no calls to the builtins that rewrite a
    namespace. Anything dynamic is refused whether or not this script can see what it does.
    A test module gives up nothing by obeying that.

    Nested scopes are exempt, as everywhere else here: a `globals()` call inside a test
    function body cannot change what the module-level assignment evaluated to.
    """
    found: set[str] = set()
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            found.add(f"from {node.module or '...'} import *")
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _DYNAMIC_BUILTINS
        ):
            found.add(f"{node.func.id}()")
        stack.extend(ast.iter_child_nodes(node))
    return found


def _const_bindings(tree: ast.Module) -> tuple[list[ast.expr], int]:
    """Module-scope bindings of CONST: readable assigned values, and everything else.

    ⚠️ BYPASS 3, found while fixing bypass 2. `extract` used to return the FIRST match from
    `ast.walk`, which is breadth-first. Python, however, uses the LAST assignment executed.
    So two module-scope assignments —

        WITNESS_RAW_COVERAGE_ALLOWLIST = frozenset({"a"})
        ...
        WITNESS_RAW_COVERAGE_ALLOWLIST = frozenset({"a", "sneaky"})

    — made the ratchet read {"a"} while the runtime allowlist was {"a", "sneaky"}. It
    reported no additions and exited 0. Reproduced. An `if/else` pair does the same thing,
    and `|=` was invisible to the old scan entirely because it only looked at Assign and
    AnnAssign nodes.

    The rule is therefore: CONST must be bound EXACTLY ONCE at module scope, by a plain
    assignment. Augmented assignment, tuple unpacking, walrus, a loop target, an import
    alias, a def or class of that name — each is a binding this script cannot resolve to a
    single value, and every one of them is refused. Nested scopes are not counted: an
    assignment inside a function body is a local and cannot change the module's value.
    """
    values: list[ast.expr] = []
    other = 0
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == CONST:
                other += 1
            continue  # a nested scope cannot rebind the module-level name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == CONST:
                    other += 1
            continue
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == CONST for t in node.targets
        ):
            values.append(node.value)
            continue
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == CONST
        ):
            if node.value is not None:
                values.append(node.value)
            continue  # a bare annotation declares a type; it binds nothing
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == CONST:
            other += 1  # |=, walrus, tuple unpacking, `for CONST in ...`, `with ... as CONST`
        stack.extend(ast.iter_child_nodes(node))
    return values, other


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
        # `builtins.frozenset = ...` rebinds the constructor for the whole module without
        # ever storing to a bare Name, so an attribute write counts too. BYPASS 4, found by
        # outside-family review of the fix for bypass 2: the ratchet read {"a"} while the
        # runtime allowlist was {"a", "sneaky"}. Reproduced before this line existed.
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            bound.add(node.attr)
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

    ⚠️ FOURTH BYPASS, found by outside-family review of the fix for the second: the rebinding
    need not store to a bare name at all. `import builtins` followed by
    `builtins.frozenset = lambda x: set(x) | {"sneaky"}` changes what the bare name resolves
    to for the whole module, while the AST shows only an attribute write. Also reproduced.

    `shadowed` therefore carries any module-scope rebinding of those constructors — by name
    OR by attribute — and a call to a shadowed name is refused rather than read.
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
