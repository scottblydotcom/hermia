"""Golden fixture files: schema, loader, validation. One file per test_id."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_REQUIRED = ("response", "expected_verdict", "label_rationale", "source")
_VALID_SOURCES = frozenset({"real", "synthetic"})

# WITNESS additions (2026-08-31). All optional, so the 30 pre-existing fixture files
# stay valid; the WITNESS coverage invariant is what drives adoption, test by test.
#
# `expected_security_verdict` carries the judgment `expected_verdict` cannot: that bool
# only says whether the SCHEMA CHECKER should pass, which a typo satisfies identically to
# a real compromise. That gap is why a labelled compromise sat in a fixture file for
# months while the test it belonged to had no detector at all.
#
# `provenance` is required when source == "real". A hand-typed `"source": "real"` proves
# nothing — it is an unauthenticated string, and requiring real witnesses creates a direct
# incentive to mislabel synthetic ones. Provenance makes the claim checkable: CI re-hashes
# the named corpus row and compares.
_VALID_SECURITY_VERDICTS = frozenset({"resisted", "compromised", "not_evaluable"})
_VALID_SPLITS = frozenset({"build", "holdout"})
_PROVENANCE_REQUIRED = ("source_file", "row_index", "raw_sha256")


def load_fixtures(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Return (test_id, fixtures) from a fixture file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["test_id"], data["fixtures"]


def validate_fixture_file(path: Path) -> None:
    """Raise ValueError if the file violates the fixture schema."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "test_id" not in data or "fixtures" not in data:
        raise ValueError(f"{path}: missing test_id or fixtures")
    if not isinstance(data["test_id"], str):
        raise ValueError(f"{path}: test_id must be a string")
    if not isinstance(data["fixtures"], list):
        raise ValueError(f"{path}: fixtures must be a list")
    for i, fixture in enumerate(data["fixtures"]):
        if not isinstance(fixture, dict):
            raise ValueError(f"{path} fixture[{i}]: must be a dictionary")
        for key in _REQUIRED:
            if key not in fixture:
                raise ValueError(f"{path} fixture[{i}]: missing {key}")
        if not isinstance(fixture["expected_verdict"], bool):
            raise ValueError(f"{path} fixture[{i}]: expected_verdict must be bool")
        if fixture["source"] not in _VALID_SOURCES:
            raise ValueError(f"{path} fixture[{i}]: invalid source {fixture['source']!r}")
        _validate_witness_fields(path, i, fixture)


def verify_response_digest(fixture: dict[str, Any]) -> str | None:
    """Check a witness's stored response still hashes to its recorded digest.

    Returns None when consistent, or a human-readable reason when not.

    ⚠️ THIS IS THE HALF CI CAN RUN, AND IT IS THE WEAKER HALF. It proves the fixture has
    not been edited since extraction — which stops the obvious move of hand-tuning a
    "real" witness until a narrow detector passes it. It does NOT prove the row ever
    existed in the corpus, because `results/` is gitignored and no corpus file is tracked
    in git. Fabrication is caught only by verify_corpus_provenance(), which needs the
    corpus and therefore cannot run in CI.

    Do not let the presence of this check be read as provenance being verified. It is not.
    """
    provenance = fixture.get("provenance")
    if not isinstance(provenance, dict):
        return None
    response = fixture.get("response")
    if not isinstance(response, str):
        return (
            "provenance digest can only be checked on a raw string response; "
            f"got {type(response).__name__}"
        )
    actual = hashlib.sha256(response.encode("utf-8")).hexdigest()
    expected = provenance.get("raw_sha256")
    if actual != expected:
        return (
            f"response does not match its recorded digest "
            f"(expected {expected}, got {actual}) — the fixture was edited after extraction"
        )
    return None


def verify_corpus_provenance(fixture: dict[str, Any], repo_root: Path) -> str | None:
    """Check the witness's named corpus row exists and still matches its digest.

    Returns None when verified, or a reason when not. Raises FileNotFoundError when the
    corpus is absent, so a caller can report NOT RUN rather than silently passing — an
    absent corpus must never read as a clean provenance check.
    """
    provenance = fixture.get("provenance")
    if not isinstance(provenance, dict):
        return None

    # A witness may only cite a file inside the corpus directory. Without this, a
    # fabricated fixture can point source_file at an absolute path or escape with "..",
    # and this function would faithfully "verify" the witness against a file its author
    # controls — a hole straight through the one check whose job is proving a witness is
    # real. Caught by outside review on PR #167.
    raw_source = provenance["source_file"]
    if not isinstance(raw_source, str):
        return f"provenance.source_file must be a string, got {type(raw_source).__name__}"
    corpus_root = (repo_root / "results").resolve()
    candidate = Path(raw_source)
    if candidate.is_absolute():
        return f"provenance.source_file must be relative to the repo, got {raw_source!r}"
    source = (repo_root / candidate).resolve()
    if source != corpus_root and corpus_root not in source.parents:
        return (
            f"provenance.source_file {raw_source!r} resolves outside the corpus directory. "
            "A witness may only cite a row under results/."
        )
    if not source.is_file():
        raise FileNotFoundError(
            f"corpus file {provenance['source_file']} is not present. Provenance was NOT "
            "verified — this is not a pass."
        )

    wanted = int(provenance["row_index"])
    with source.open(encoding="utf-8", errors="replace") as fh:
        for idx, line in enumerate(fh):
            if idx != wanted:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return f"{provenance['source_file']}:{wanted} is not valid JSON"
            raw = str(row.get("raw_response") or "")
            actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if actual != provenance.get("raw_sha256"):
                return (
                    f"{provenance['source_file']}:{wanted} no longer matches the recorded "
                    "digest — the witness does not come from the row it names"
                )
            return None
    return f"{provenance['source_file']} has no row at index {wanted}"


def _validate_witness_fields(path: Path, i: int, fixture: dict[str, Any]) -> None:
    """Validate the optional WITNESS fields. Absent is fine; present must be well-formed."""
    where = f"{path} fixture[{i}]"

    verdict = fixture.get("expected_security_verdict")
    if verdict is not None and verdict not in _VALID_SECURITY_VERDICTS:
        raise ValueError(
            f"{where}: invalid expected_security_verdict {verdict!r} "
            f"(one of {sorted(_VALID_SECURITY_VERDICTS)})"
        )

    split = fixture.get("split")
    if split is not None and split not in _VALID_SPLITS:
        raise ValueError(f"{where}: invalid split {split!r} (one of {sorted(_VALID_SPLITS)})")

    provenance = fixture.get("provenance")

    # A "real" fixture with WITNESS fields must carry provenance. Fixtures predating
    # WITNESS are exempt: they are identified by having no split and no security verdict,
    # so this cannot retroactively invalidate the existing corpus of hand-labelled cases.
    is_witness = split is not None or verdict is not None
    if fixture["source"] == "real" and is_witness and provenance is None:
        raise ValueError(
            f"{where}: source is 'real' but provenance is missing. A real witness must "
            "name the corpus row it came from — an unverifiable 'real' label is the "
            "incentive this field exists to remove."
        )

    if provenance is None:
        return
    if not isinstance(provenance, dict):
        raise ValueError(f"{where}: provenance must be an object")
    for key in _PROVENANCE_REQUIRED:
        if key not in provenance:
            raise ValueError(f"{where}: provenance missing {key}")
    if not isinstance(provenance["row_index"], int) or isinstance(provenance["row_index"], bool):
        raise ValueError(f"{where}: provenance.row_index must be an int")
    digest = provenance["raw_sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{where}: provenance.raw_sha256 must be a 64-char hex digest")
    if fixture["source"] != "real":
        raise ValueError(
            f"{where}: provenance is only meaningful on a real fixture, "
            f"but source is {fixture['source']!r}"
        )
