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

# A SECOND ratchet, in the opposite direction. SECURITY_TEST_IDS is the coverage guard's
# SCOPE: it computes `uncovered = set(SECURITY_TEST_IDS) - covered`. Remove an id from it and
# the blind spot becomes invisible with the allowlist untouched, the guard green and this
# ratchet green — the same shape as every bypass above, one level up. That is exactly the
# drift SECURITY_TEST_IDS exists to prevent, and how the original GREEN-while-blind bug
# happened. So: the allowlist may only shrink, and the scope may only grow.
# A SECOND shrink-only register, with a DIFFERENT meaning from the first. The raw-coverage
# allowlist answers "is a detector configured?" — membership. This one answers "has a detector
# ever been shown to fire?" — behaviour. Conflating them would make one list mean two things,
# and since both may only shrink, that muddle would be permanent. Asserting membership as a
# proxy for behaviour is the precise error this framework exists to catch.
UNPROVEN_CONST = "WITNESS_UNPROVEN_DETECTOR_ALLOWLIST"

SCOPE_CONST = "SECURITY_TEST_IDS"
SCOPE_TARGET = "src/hermia/schemas.py"

WORKFLOW = ".github/workflows/witness-ratchet.yml"

# The allowlist may only shrink — but "never grows" is not survivable. A security test can
# legitimately enter the registry before anyone has built a detector for it, and refusing that
# outright would just push people to route around this script.
#
# So widening is possible and DELIBERATELY expensive: the change must declare, in the same file,
# exactly which ids it is adding and why. The declaration must match the additions EXACTLY —
# no more, no less — so it can neither authorize a silent extra entry nor be written in advance.
#
# It also cannot linger. Once an id reaches the base ref it is in the allowlist proper, and a
# declaration still naming it is STALE and fails the build. A widening is a one-shot token that
# must be spent and then removed; it can never become a standing permission.
#
# ⚠️ Be honest about what this buys. It does NOT stop someone with merge rights from adding an
# entry and its justification in one diff. It makes widening LOUD, attributable and reviewed
# instead of a silent line in a frozenset — which is the whole thing the ratchet was ever for.
WIDENING_CONST = "WITNESS_ALLOWLIST_WIDENING"
_MIN_REASON = 40

# Guards that live in TARGET and must stay alive. The equivalence guard is the load-bearing
# one: it compares what this script reads statically against what Python actually produces,
# inside the real pytest session. That is the only decidable sensor for the whole bypass
# class, and it is deletable in the same diff — which is what these checks stop.
GUARD_REFERENCES = {
    "test_every_security_test_has_compromise_markers": (SCOPE_CONST, CONST),
    "test_witness_allowlist_only_shrinks": (SCOPE_CONST, CONST),
    "test_witness_allowlist_is_defined_readably": ("extract", CONST),
    # Phase 2's invariant and its companion. Without these, the completeness contract itself
    # could be deleted while every other guard stayed green — which is precisely the shape of
    # the bug this project exists to catch. Registered a change later than they should have
    # been, because the guards had to exist on the base ref first. Flagged by CodeRabbit.
    "test_every_security_test_has_a_firing_compromise_witness": (SCOPE_CONST, "_fixture_witnesses"),
    "test_allowlisted_blind_spots_are_still_blind": (UNPROVEN_CONST, "_fixture_witnesses"),
    "test_witness_unproven_allowlist_is_defined_readably": ("extract", UNPROVEN_CONST),
    "test_every_security_test_has_a_fixture_file": (SCOPE_CONST, "is_file"),
}
_CONSTRUCTORS = frozenset({"frozenset", "set"})

# Builtins that can rewrite the module namespace without any visible binding. A test module
# has no business calling these at module scope, and each of them defeats static reading.
_DYNAMIC_BUILTINS = frozenset(
    {"globals", "locals", "vars", "exec", "eval", "setattr", "delattr", "__import__"}
)


def extract(source: str, origin: str, const: str = CONST) -> set[str] | None:
    """Pull the allowlist's string literals out of `source` without executing it.

    Returns None when the constant is absent, which the caller distinguishes: absent on
    the BASE is the bootstrap case (this is the change introducing it); absent on HEAD
    means it was deleted or renamed, which must fail.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - malformed base is a real failure
        raise SystemExit(f"FAIL: could not parse {origin}: {exc}") from exc

    reaching_in = _namespace_writes_from_any_scope(tree, const)
    if reaching_in:
        raise SystemExit(
            f"FAIL: {origin} rebinds the module namespace via {', '.join(sorted(reaching_in))}. "
            f"That can change {const} from inside a function body, where this script "
            "deliberately does not look, so what it reads would not be what Python uses."
        )

    dynamic = _dynamic_constructs(tree)
    if dynamic:
        raise SystemExit(
            f"FAIL: {origin} uses {', '.join(sorted(dynamic))} at module scope. That can "
            f"rebind {const} with nothing for this script to read, so the allowlist it "
            "compares would not be the one Python uses. Module scope must stay statically "
            "readable; move dynamic code inside a function."
        )

    shadowed = _CONSTRUCTORS & _module_scope_bindings(tree)
    values, other = _const_bindings(tree, const)

    if other or len(values) > 1:
        raise SystemExit(
            f"FAIL: {const} in {origin} is bound {len(values) + other} times at module "
            "scope, or bound in a form this script cannot resolve. It must be assigned "
            "exactly once, as a plain literal. Python uses the LAST binding executed while "
            "this script would have to guess which one that is — and guessing wrong is how "
            "a ratchet passes while the allowlist grows."
        )

    if not values:
        return None
    return _literal_strings(values[0], origin, shadowed, const)


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
            stack.extend(_definition_header_nodes(node))  # header runs in the enclosing scope
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


def _definition_header_nodes(node: ast.AST) -> list[ast.AST]:
    """Expressions in a def/class HEADER, which evaluate in the ENCLOSING scope.

    Every traversal here skips function and class BODIES, because a name bound there is a
    local. Their headers are different: decorators, argument defaults, annotations, class
    bases and class keywords all execute where the definition appears, at module scope, at
    definition time. Skipping the whole node skipped those too.

    Flagged by CodeRabbit on PR #167. The exploits reachable through it all routed via the
    attribute-store gap below, so no header-only bypass was demonstrated — but the traversal
    gap is real, and given how this file has gone, an undemonstrated gap is not a safe one.
    """
    out: list[ast.AST] = list(getattr(node, "decorator_list", []))
    if isinstance(node, ast.ClassDef):
        out.extend(node.bases)
        out.extend(kw.value for kw in node.keywords)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        spec = node.args
        out.extend(d for d in [*spec.defaults, *spec.kw_defaults] if d is not None)
        for arg in [*spec.posonlyargs, *spec.args, *spec.kwonlyargs, spec.vararg, spec.kwarg]:
            if arg is not None and arg.annotation is not None:
                out.append(arg.annotation)
        if node.returns is not None:
            out.append(node.returns)
    return out


def _assigned_values(node: ast.AST) -> list[ast.expr]:
    """Right-hand sides of any assignment form, so an alias can be spotted wherever it is made."""
    if isinstance(node, ast.Assign):
        return [node.value]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
        return [node.value]
    if isinstance(node, ast.NamedExpr):
        return [node.value]
    return []


def _namespace_writes_from_any_scope(tree: ast.Module, const: str) -> set[str]:
    """Rebindings of the module namespace reachable from INSIDE a function body.

    ⚠️ BYPASSES 7 AND 8, found by outside-family review of the fix for 5 and 6. Every other
    check here exempts nested scopes, because a name bound inside a function is a local and
    this module's own tests legitimately call importlib and globals in their bodies. That
    exemption was itself the hole:

        def add():
            global WITNESS_RAW_COVERAGE_ALLOWLIST
            WITNESS_RAW_COVERAGE_ALLOWLIST = frozenset({"a", "sneaky"})
        add()

        def add():
            globals()["WITNESS_RAW_COVERAGE_ALLOWLIST"] = frozenset({"a", "sneaky"})
        add()

    Both reproduced: ratchet read {"a"}, runtime was {"a", "sneaky"}. Note the call need not
    even be at module scope — any test or fixture that runs before the coverage test would do.

    So these two patterns are refused from ANY scope. They are named precisely rather than
    by blanket-refusing nested code: `global` naming the constant or a constructor, and an
    assignment through a `globals()`/`vars()` subscript. A bare `return globals()` stays
    legal, because it rebinds nothing.
    """
    watched = {const} | _CONSTRUCTORS
    found: set[str] = set()

    # BYPASS 19, found by CodeRabbit on PR #171. Every check above matches a bare Name, so
    # reaching the same builtin through the module qualified it out of view:
    #     import builtins;      builtins.setattr(builtins, "frozenset", ...)
    #     import builtins as b; b.setattr(b, "frozenset", ...)
    # Both reproduced. The names the builtins module is bound to are collected first, because
    # `monkeypatch.setattr` is ALSO an Attribute call and must stay legal — this repo uses it in
    # several test modules, and a rule that failed innocent pytest code would get the gate
    # switched off rather than obeyed. So the check is on the receiver, not the attribute name.
    builtins_aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "builtins"
    }
    for node in ast.walk(tree):
        target = node.func if isinstance(node, ast.Call) else node
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id in builtins_aliases
            and target.attr in _DYNAMIC_BUILTINS | _CONSTRUCTORS | {"getattr"}
        ):
            # `getattr` is deliberately absent from _DYNAMIC_BUILTINS — bare getattr is ordinary
            # Python and banning it would fail the build on innocent code. Reached THROUGH the
            # builtins module it has no innocent use: you would simply write `getattr`.
            found.add(f"{target.value.id}.{target.attr}")

    # BYPASS 15 AND 16, and the reason this refuses a CLASS rather than a list of forms.
    #
    # Every dynamic-builtin check matched on the NAME at the call site, so binding the builtin
    # to another name defeated all of them at once (qwen3.5:122b). Fixing only the assignment
    # form left three more ways in, found by CodeRabbit and by probing around its finding:
    #     def rewrite(g=globals): ...      # a parameter default binds without an assignment
    #     f(globals)                       # passed as an argument
    #     def pick(): return globals       # returned from a helper
    # All reproduced: the ratchet read the old literal while runtime widened the namespace.
    #
    # So the rule is not "these binding forms are refused" — that list does not terminate, as
    # fifteen bypasses have already demonstrated. A reference to one of these builtins is
    # allowed ONLY as the direct callee of a call. Used as a VALUE in any other position it is
    # refused, whatever syntax carries it there.
    called_directly = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in _DYNAMIC_BUILTINS
            and id(node) not in called_directly
        ):
            found.add(f"referencing {node.id} as a value")

    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            hit = watched.intersection(node.names)
            if hit:
                found.add(f"`global {', '.join(sorted(hit))}`")
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        for target in targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Call)
                and isinstance(target.value.func, ast.Name)
                and target.value.func.id in {"globals", "vars"}
            ):
                found.add(f"assignment through {target.value.func.id}()")
            # BYPASS 11, found by CodeRabbit on PR #167 and reproduced. _module_scope_bindings
            # records attribute stores, but only at module scope. A function body may do
            # `import builtins; builtins.frozenset = ...` and be called before the module
            # assigns the allowlist; ratchet read {"a"}, runtime was {"a", "s"}.
            if isinstance(target, ast.Attribute) and target.attr in watched:
                found.add(f"attribute write to {target.attr}")

        # BYPASSES 9 AND 10. `exec` and `eval` are refused at module scope, but not inside a
        # function body, where nothing is inspected:
        #     def f(): exec("ALLOWLIST = frozenset({'a','sneaky'})", globals())
        #     f()
        # Both reproduced. The general move is handing the module dict to something that can
        # write to it, so that is what is refused — from any scope, whatever the callee.
        # Passing a fresh dict stays legal, which matters: this module's own regression tests
        # call exec(compile(...), namespace) with a local dict to drive the attacks.
        # BYPASS 17, found by CodeRabbit on PR #169. setattr and delattr were refused at
        # MODULE scope only, and the attribute-store rule sees `builtins.frozenset = ...` but
        # not `setattr(builtins, "frozenset", ...)`, which is a Call. From inside a function
        # body, nothing looked:
        #     def f(): setattr(builtins, "frozenset", lambda x: set(x) | {"s"})
        #     f()
        # Reproduced. Unlike globals(), which is harmless until something writes through it,
        # setattr IS the write — so the call is refused wherever it appears. `monkeypatch.
        # setattr` is an Attribute call, not a Name, so ordinary pytest code is unaffected.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"setattr", "delattr"}
        ):
            found.add(f"a {node.func.id}() call")

        # BYPASS 18, found by CodeRabbit on PR #171: the check above matches a direct Name
        # callee, so fetching the same builtin indirectly walked past it —
        #     getattr(builtins, "setattr")(builtins, "frozenset", ...)
        # Reproduced. Naming one of these builtins in a getattr literal is refused; getattr
        # itself stays legal, because it is ordinary Python and banning it outright would fail
        # the build on innocent code.
        #
        # ⚠️ A COMPUTED name still evades this, and that is fine rather than a gap left open:
        # the load-bearing control is the equivalence guard, which compares this script's
        # static read against the value Python actually produces and catches ANY divergence
        # however it was caused — verified against this very bypass. That guard is registered
        # in GUARD_REFERENCES, so it cannot be removed without a liveness failure. This layer
        # is defence in depth, not the thing holding the roof up.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _DYNAMIC_BUILTINS | _CONSTRUCTORS
        ):
            found.add(f"getattr(..., {node.args[1].value!r})")

        if isinstance(node, ast.Call):
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                if (
                    isinstance(arg, ast.Call)
                    and isinstance(arg.func, ast.Name)
                    and arg.func.id in {"globals", "vars"}
                ):
                    found.add(f"passing {arg.func.id}() into a call")
    return found


def _const_bindings(tree: ast.Module, const: str) -> tuple[list[ast.expr], int]:
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
            if node.name == const:
                other += 1
            stack.extend(_definition_header_nodes(node))  # header runs in the enclosing scope
            continue  # ...but the BODY is a nested scope and cannot rebind the module name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == const:
                    other += 1
            continue
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == const for t in node.targets
        ):
            values.append(node.value)
            continue
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == const
        ):
            if node.value is not None:
                values.append(node.value)
            continue  # a bare annotation declares a type; it binds nothing
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == const:
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
            stack.extend(_definition_header_nodes(node))  # header runs in the enclosing scope
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


def _literal_strings(
    value: ast.expr, origin: str, shadowed: frozenset[str] | set[str], const: str
) -> set[str]:
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
                f"FAIL: {const} in {origin} is built by calling {func.id!r}, but {func.id!r} "
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
            f"FAIL: {const} in {origin} is not a literal set of strings, so this script "
            "cannot read it statically. That is not an empty allowlist — it is an "
            "unreadable one, and passing here would silently disable the ratchet forever. "
            "Define it inline as a literal frozenset({...}) of string constants, or update "
            "this script deliberately in the same change."
        )

    out: set[str] = set()
    for element in inner:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            raise SystemExit(
                f"FAIL: {const} in {origin} contains a non-literal entry "
                f"({type(element).__name__}). Every entry must be a plain string constant "
                "so the ratchet can compare it against the base ref."
            )
        out.add(element.value)
    return out


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run git in the repo. The gate shells out to git and NOTHING else, ever.

    A missing git binary used to raise FileNotFoundError and surface as an internal error,
    which reads as an infrastructure hiccup rather than as the gate not having run. Found by
    qwen3.5:122b. Fail closed and say so.
    """
    try:
        return subprocess.run(
            ["git", *argv], cwd=repo, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        print(f"FAIL: could not execute git ({exc}). The ratchet has NOT run — not a pass.")
        raise SystemExit(1) from exc


def _exists_at_ref(repo: Path, ref: str, path: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{ref}:{path}").returncode == 0


def _guard_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in GUARD_REFERENCES
    }


def _guard_fingerprint(node: ast.FunctionDef) -> str:
    """A guard's body with its docstring stripped, so prose edits are free and gutting is not."""
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return ast.dump(ast.Module(body=body, type_ignores=[]))


def _always_true(expr: ast.expr) -> bool:
    """True when an expression is a TAUTOLOGY by structure, whatever its names hold.

    Found by qwen3.5:122b. `_is_literal_only` rejects `assert True`, but referencing the
    guarded name defeats it: `assert WITNESS_RAW_COVERAGE_ALLOWLIST or True` contains a Name,
    so it passed the literal-only test while being unconditionally true. So do
    `assert True or CONST` and `assert not (CONST and False)`.

    Note the family difference: gpt-oss proposed `assert (1 == 2) or True` for the same slot,
    which was ALREADY caught — it has no Name at all. Only the version that mentions the guarded
    name gets through, which is exactly the version a neutered guard would use.

    Constant-folds the boolean skeleton and treats every name, call and comparison as unknown.
    That catches the tautologies a neutered guard actually reaches for. It does NOT catch every
    inert assertion — `assert len(CONST) >= 0` is inert and undecidable in general — and that is
    the standing scope limit: liveness proves a guard ACTIVE, never EFFECTIVE.
    """
    if isinstance(expr, ast.Constant):
        return bool(expr.value)
    if isinstance(expr, ast.BoolOp):
        if isinstance(expr.op, ast.Or):
            return any(_always_true(v) for v in expr.values)
        return all(_always_true(v) for v in expr.values)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _always_false(expr.operand)
    return False


def _always_false(expr: ast.expr) -> bool:
    """Mirror of _always_true, so `not (X and False)` folds correctly."""
    if isinstance(expr, ast.Constant):
        return not bool(expr.value)
    if isinstance(expr, ast.BoolOp):
        if isinstance(expr.op, ast.And):
            return any(_always_false(v) for v in expr.values)
        return all(_always_false(v) for v in expr.values)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _always_true(expr.operand)
    return False


def _is_literal_only(expr: ast.expr) -> bool:
    """True when an expression can only ever evaluate to the same thing.

    `assert True` was rejected by checking for ast.Constant, and `assert 1 == 1` walked straight
    past it because a Compare is not a Constant — a guard could keep its required-name
    references and still enforce nothing. Found by CodeRabbit on PR #170. An expression that
    reads no name, attribute, subscript or call has no input and cannot depend on the state the
    guard exists to check.
    """
    return not any(
        isinstance(n, (ast.Name, ast.Attribute, ast.Subscript, ast.Call))
        for n in ast.walk(expr)
    )


def _guard_liveness_problems(tree: ast.Module) -> list[str]:
    """Each guard must still exist, still assert, and still mention what makes it a guard.

    This proves a guard is ACTIVE. It does NOT prove it is EFFECTIVE — a guard can be made
    useless while satisfying every check here. That is the WITNESS scope limit and it must not
    drift; outside review has broken an overstated version of this claim twice.

    Deliberately weak in one respect: it requires an `assert` somewhere in the body, not an
    assert whose condition reaches the required names. The stronger form was prototyped and
    FALSE-POSITIVED on the real, correct guards, which compute intermediates
    (`unexpected = sorted(uncovered - ALLOWLIST)` then `assert not unexpected`). Rejected on
    evidence rather than taste.
    """
    found = _guard_nodes(tree)
    problems: list[str] = []
    for name, required in GUARD_REFERENCES.items():
        node = found.get(name)
        if node is None:
            problems.append(f"{name} is missing from {TARGET} (deleted or renamed)")
            continue
        asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
        if not asserts:
            problems.append(f"{name} contains no assert — it can no longer fail")
        elif all(_is_literal_only(a.test) or _always_true(a.test) for a in asserts):
            # `assert True` alongside a bare reference to the required names satisfied both the
            # has-an-assert and mentions-the-names checks while enforcing nothing. Found by
            # gpt-oss:120b. This does not make liveness prove EFFECTIVENESS — nothing here can
            # — but a guard whose every assertion is a literal cannot fail by construction.
            problems.append(
                f"{name} has no assertion that can fail — every one is a literal or a "
                "tautology, whatever names it mentions"
            )
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
        }
        missing = [r for r in required if r not in names]
        if missing:
            problems.append(f"{name} no longer references {', '.join(missing)}")
    return problems


def _guard_change_problems(repo: Path, base: str, allowlist_changed: bool) -> list[str]:
    """Refuse to move the allowlist in the same diff that changes what guards it.

    Uses the MERGE BASE, not the branch tip: the question is "did THIS pull request touch the
    guards", and a three-dot comparison is the only one that answers it without accusing the
    branch of everything that landed on the base meanwhile. The allowlist comparison keeps
    using the branch tip, because there the question is different — "is this re-introducing an
    entry the base already removed" — and tip is what catches a stale branch. Two refs, two
    questions, each picked for its failure direction.
    """
    if not allowlist_changed:
        return []
    merge_base = _git(repo, "merge-base", base, "HEAD").stdout.strip()
    if not merge_base:
        return [f"could not compute a merge base with {base}"]

    problems: list[str] = []
    changed = set(
        _git(repo, "diff", "--name-only", f"{merge_base}...HEAD").stdout.split()
    )
    for path in (WORKFLOW, "scripts/witness_allowlist_ratchet.py"):
        if path in changed:
            problems.append(f"{path} is modified in the same change as the allowlist")

    old = _git(repo, "show", f"{merge_base}:{TARGET}")
    if old.returncode == 0:
        try:
            before = _guard_nodes(ast.parse(old.stdout))
        except SyntaxError:
            return [*problems, f"could not parse {TARGET} at {merge_base}"]
        now = _guard_nodes(ast.parse((repo / TARGET).read_text(encoding="utf-8")))
        for name, node in before.items():
            fresh = now.get(name)
            if fresh is None or _guard_fingerprint(fresh) != _guard_fingerprint(node):
                problems.append(f"{name} is modified in the same change as the allowlist")
    return problems


def _extract_widening(source: str, origin: str) -> dict[str, str] | None:
    """Read the widening declaration: a module-scope dict of {test_id: reason} string literals.

    Same discipline as the allowlist — refuse anything that cannot be resolved statically,
    rather than guessing. Returns None when the declaration is absent, which means no widening
    is authorised at all.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - the caller already parsed HEAD
        raise SystemExit(f"FAIL: could not parse {origin}: {exc}") from exc

    values, other = _const_bindings(tree, WIDENING_CONST)
    if other or len(values) > 1:
        raise SystemExit(
            f"FAIL: {WIDENING_CONST} in {origin} is bound more than once, or in a form this "
            "script cannot resolve. Declare it exactly once, as a plain dict literal."
        )
    if not values:
        return None

    node = values[0]
    if not isinstance(node, ast.Dict):
        raise SystemExit(
            f"FAIL: {WIDENING_CONST} in {origin} is not a literal dict, so this script cannot "
            "read which additions it claims to authorise. Write it inline as "
            '{"test-id": "reason", ...} with string literals only.'
        )

    out: dict[str, str] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        ok_key = isinstance(key, ast.Constant) and isinstance(key.value, str)
        ok_val = isinstance(value, ast.Constant) and isinstance(value.value, str)
        if not (ok_key and ok_val):
            raise SystemExit(
                f"FAIL: {WIDENING_CONST} in {origin} contains a non-literal key or value. "
                "Every entry must be a plain string constant so the ratchet can compare it."
            )
        out[key.value] = value.value
    return out


def _widening_problems(
    widening: dict[str, str] | None, added: set[str], base: set[str]
) -> list[str]:
    """Does the declaration authorise exactly these additions, and nothing else?"""
    problems: list[str] = []

    declared = set(widening or {})

    stale = sorted(declared & base)
    for entry in stale:
        problems.append(
            f"{entry!r} is declared in {WIDENING_CONST} but is already in the allowlist at the "
            "base ref. A spent widening must be deleted, not left standing."
        )

    # ⚠️ Checked whether or not this diff adds anything. It used to sit behind an
    # `if not added: return problems` early exit, which let a declaration land on its own —
    # and that is a two-step, not an oversight. PR1 lands only the declaration and passes;
    # PR2 then adds the id, matching a declaration ALREADY on the base, so `undeclared` is
    # empty and `stale` does not fire because the id is not yet in the allowlist. The
    # justification and the addition are never reviewed in the same diff, which was the one
    # thing this mechanism existed to guarantee. Found by Antigravity on PR #168, reproduced.
    unused = sorted(declared - added - base)
    for entry in unused:
        problems.append(
            f"{entry!r} is declared in {WIDENING_CONST} but is not actually being added — a "
            "declaration that outlives its own diff is a standing permission, which is exactly "
            "what this must never become"
        )

    if not added:
        return problems

    if widening is None:
        return [
            *problems,
            f"the allowlist grows by {len(added)} entr"
            f"{'y' if len(added) == 1 else 'ies'} with no {WIDENING_CONST} declaration at all",
        ]

    undeclared = sorted(added - set(widening))
    for entry in undeclared:
        problems.append(f"{entry!r} is being added but is not declared in {WIDENING_CONST}")

    for entry in sorted(added & set(widening)):
        reason = widening[entry].strip()
        if len(reason) < _MIN_REASON:
            problems.append(
                f"{entry!r} is declared with a {len(reason)}-character reason; a widening needs "
                f"an actual justification (at least {_MIN_REASON} characters) that a reviewer "
                "can weigh"
            )
    return problems


def _register_added(repo: Path, base_ref: str, const: str) -> tuple[int, set[str], set[str]]:
    """(status, added, base_entries) for one shrink-only register. status is an exit code.

    Additions are computed for EVERY register before the widening declaration is validated,
    because one change may legitimately widen more than one of them and the declaration covers
    all of it at once. Validating per register rejected a declared id destined for the other
    register as an unused declaration, making a simultaneous widening impossible and blaming
    the declaration for it. Caught by CodeRabbit on PR #168 and reproduced before fixing.
    """
    head, base = _read_const(repo, base_ref, TARGET, const)

    if head is None and base is None:
        return 0, set(), set()

    if head is None:
        print(f"FAIL: {const} existed at {base_ref} but is missing from {TARGET} in the working "
              "tree.")
        print(
            "The ratchet cannot verify a register that was deleted or renamed. If that was "
            "deliberate, land that change on its own, reviewed, first."
        )
        return 1, set(), set()

    base_entries: set[str] = set() if base is None else base
    return 0, head - base_entries, base_entries


def _report_register(
    const: str, added: set[str], removed: set[str], widening: dict[str, str] | None
) -> None:
    """Print what one register did. The declaration is validated by the caller, once, across
    every register — see _register_added for why per-register validation was wrong."""
    for entry in sorted(removed):
        print(f"  {const} removed (good):  {entry}")
    if not added:
        return
    print()
    print(f"WIDENING: {const} gains {len(added)} entr{'y' if len(added) == 1 else 'ies'}, "
          f"declared in {WIDENING_CONST} and therefore recorded rather than silent:")
    for entry in sorted(added):
        print(f"  ADDED: {entry}")
        print(f"    {(widening or {})[entry]}")


def _read_const(
    repo: Path, base: str, target: str, const: str
) -> tuple[set[str] | None, set[str] | None]:
    """(head, base) values of `const` in `target`. Raises SystemExit if the base is unreadable."""
    head = extract((repo / target).read_text(encoding="utf-8"), "working tree", const)
    shown = _git(repo, "show", f"{base}:{target}")
    if shown.returncode != 0:
        print(f"FAIL: could not read {target} at {base}: {shown.stderr.strip()}")
        print("If the base ref is unavailable the ratchet has NOT run — this is not a pass.")
        raise SystemExit(1)
    return head, extract(shown.stdout, base, const)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main", help="base ref to compare against")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]

    # ---- 1. The guards must be alive. Checked ALWAYS, bootstrap included.
    #
    # This is the centre of the design, and it is an inversion of what this script used to
    # try to do. Predicting HEAD's runtime value from its source is undecidable, which is why
    # eleven bypasses fitted through it. The decidable sensor already exists: the pytest test
    # that compares this script's static read against the value Python actually produces,
    # inside the real pytest session. Its only weakness was that it lives in the file it
    # judges and could be deleted by the same diff that exploits it. So the gate no longer
    # tries to out-parse the adversary; it makes that test undeletable.
    try:
        head_tree = ast.parse((repo / TARGET).read_text(encoding="utf-8"))
    except OSError as exc:
        # A deleted or unreadable target used to raise FileNotFoundError and surface as an
        # internal error, which reads as an infrastructure hiccup rather than as the gate not
        # having run — and deleting the file is the most direct way to remove every guard at
        # once. Found by qwen3.5:122b.
        print(f"FAIL: could not read {TARGET}: {exc}")
        print("The ratchet has NOT run — this is not a pass.")
        return 1
    except SyntaxError as exc:
        print(f"FAIL: could not parse {TARGET}: {exc}")
        print("The ratchet has NOT run — this is not a pass.")
        return 1

    problems = _guard_liveness_problems(head_tree)
    if problems:
        print(f"FAIL: the WITNESS guards in {TARGET} are not intact.")
        for problem in problems:
            print(f"  {problem}")
        print()
        print(
            "These guards are what make the allowlist meaningful; the equivalence guard is "
            "the only thing that detects this script reading a different allowlist than "
            "Python uses. The ratchet has NOT run — this is not a pass. Restore them."
        )
        return 1

    # ---- 2. Bootstrap is permitted only while this gate does not yet exist on the base.
    #
    # It used to be permitted whenever the constant was absent from the base, unconditionally,
    # for a head of any size — so renaming the constant re-baselined the ratchet silently and
    # forever. Anchoring it to the workflow's own presence means bootstrap can happen exactly
    # once per base branch and can never recur.
    bootstrapping = not _exists_at_ref(repo, args.base, WORKFLOW)

    head, base = _read_const(repo, args.base, TARGET, CONST)

    if head is None:
        print(f"FAIL: {CONST} is missing from {TARGET} in the working tree.")
        print(
            "The ratchet cannot verify an allowlist that was deleted or renamed. If that "
            "was deliberate, land that change on its own, reviewed, first."
        )
        return 1

    if base is None and not bootstrapping:
        print(f"FAIL: {CONST} is absent from {TARGET} at {args.base}, but this gate already "
              f"runs there ({WORKFLOW} exists at the base).")
        print(
            "That is a rename or deletion, not a bootstrap, and treating it as one would "
            "re-baseline the ratchet to whatever this change contains. The ratchet has NOT "
            "run — this is not a pass."
        )
        return 1

    # ---- 3. Guards and gate may not move in the same diff as EITHER register.
    #
    # `changed` used to be computed from the raw-coverage allowlist alone, so a change that
    # moved only WITNESS_UNPROVEN_DETECTOR_ALLOWLIST could rewrite this script, the workflow or
    # the guard tests in the same diff and skip this check entirely. Every shrink-only register
    # has to count. Found by Antigravity on PR #168.
    unproven_rc, unproven_added, unproven_base = _register_added(repo, args.base, UNPROVEN_CONST)
    if unproven_rc:
        return unproven_rc
    unproven_head, _unproven_base_raw = _read_const(repo, args.base, TARGET, UNPROVEN_CONST)

    if not bootstrapping:
        changed = (
            base is None
            or head != base
            or bool(unproven_added)
            or bool(unproven_base - (unproven_head or set()))
        )
        guard_problems = _guard_change_problems(repo, args.base, changed)
        if guard_problems:
            print("FAIL: the allowlist moved in the same change as the machinery guarding it.")
            for problem in guard_problems:
                print(f"  {problem}")
            print()
            print(
                "Changing a guard and the thing it guards in one diff is the two-step this "
                "gate exists to defeat, whether or not it was meant that way. Land the guard "
                "change on its own, reviewed, first. The ratchet has NOT run — this is not a "
                "pass."
            )
            return 1

    # ---- 4. The scope may only GROW, mirroring the allowlist rule.
    scope_head, scope_base = _read_const(repo, args.base, SCOPE_TARGET, SCOPE_CONST)
    if scope_head is None:
        print(f"FAIL: {SCOPE_CONST} is missing from {SCOPE_TARGET} in the working tree.")
        print("The ratchet has NOT run — this is not a pass.")
        return 1
    if scope_base is not None:
        dropped = sorted(scope_base - scope_head)
        if dropped:
            print(f"FAIL: {SCOPE_CONST} may only grow.")
            for identifier in dropped:
                print(f"  REMOVED: {identifier}")
            print()
            print(
                "Removing a security test from the guard's scope hides a blind spot without "
                "touching the allowlist at all — the guard stays green because it never looks "
                "at that test again. If a test genuinely is not a security test, that needs "
                "an explicit decision recorded on the pull request."
            )
            return 1

    # ---- 4b. Both shrink-only registers, validated together.
    #
    # The declaration is checked ONCE against every register's additions at the same time. One
    # change may legitimately widen more than one register, and validating them separately
    # rejected a declared id destined for the other register as an "unused declaration" —
    # making a valid simultaneous widening impossible, and blaming the declaration for it.
    widening = _extract_widening((repo / TARGET).read_text(encoding="utf-8"), "working tree")

    primary_base: set[str] = set() if base is None else base
    primary_added = head - primary_base

    # ⚠️ A genuine bootstrap — this gate does not exist at the base ref at all — establishes the
    # BASELINE. Its entries are not additions and cannot be declared, because there is nothing
    # to declare them against. Validating them as additions demanded a justification for every
    # pre-existing entry, failed, and made the bootstrap handler below unreachable. That was
    # live: `main` is still pre-allowlist, so the next dev->main promotion would have failed a
    # required check with a message blaming a declaration that was not the problem. Found by
    # Antigravity on PR #168 and reproduced against origin/main.
    all_added = set() if bootstrapping else (primary_added | unproven_added)
    all_base = primary_base | unproven_base
    widening_problems = _widening_problems(widening, all_added, all_base)

    if widening_problems:
        print()
        print("FAIL: the WITNESS registers may only shrink.")
        for entry in sorted(all_added):
            print(f"  ADDED: {entry}")
        print()
        for problem in widening_problems:
            print(f"  {problem}")
        print()
        print(
            "Each entry is a security test whose compromises cannot be detected. Adding one "
            f"widens a declared blind spot. If that is genuinely intended, declare it in "
            f"{WIDENING_CONST} as {{test_id: reason}} in the same change — an explicit decision "
            "recorded where a reviewer reads it, not a silent line."
        )
        return 1

    _report_register(
        UNPROVEN_CONST,
        unproven_added,
        unproven_base - (unproven_head or set()),
        widening,
    )

    # ---- 5. The allowlist itself may only shrink.
    if base is None:
        print(f"BOOTSTRAP: {CONST} does not exist at {args.base}, and neither does {WORKFLOW}.")
        print(f"This is the change that introduces both, with {len(head)} entr"
              f"{'y' if len(head) == 1 else 'ies'}:")
        for entry in sorted(head):
            print(f"  {entry}")
        print(f"Guards verified alive: {', '.join(sorted(GUARD_REFERENCES))}.")
        print(f"{SCOPE_CONST}: {len(scope_head)} ids. Subsequent changes are compared to this.")
        return 0

    added = sorted(head - base)
    removed = sorted(base - head)

    print(f"base ({args.base}): {len(base)} entr{'y' if len(base) == 1 else 'ies'}")
    print(f"head:              {len(head)} entr{'y' if len(head) == 1 else 'ies'}")
    for entry in removed:
        print(f"  removed (good):  {entry}")

    if added:
        print()
        print(f"WIDENING: {len(added)} entr{'y' if len(added) == 1 else 'ies'} added, declared "
              f"in {WIDENING_CONST} and therefore recorded rather than silent:")
        for entry in added:
            print(f"  ADDED: {entry}")
            print(f"    {(widening or {})[entry]}")
        print()
        print(
            "This is a deliberate widening of a declared blind spot. The ratchet permits it "
            "ONLY because it is written down; it does not endorse it. The declaration must be "
            "deleted once these entries reach the base ref."
        )

    print(f"OK: both WITNESS registers shrank or held; guards alive; "
          f"{SCOPE_CONST} did not shrink.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
