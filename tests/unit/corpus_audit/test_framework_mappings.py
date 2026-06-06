"""Tripwire for CSA MAESTRO + NIST AI RMF mappings in the runtime dataset.

MAESTRO single-layer mapping was audited 2026-06-06 against the official CSA paper
(Huang 2025); see docs/maestro-reference.md. NIST AI RMF audit pending.
"""
from hermia.runner import load_tests_all

_BY_ID = {t["id"]: t for t in load_tests_all()}

# Audited 2026-06-06. Single layer per test. Two reasoning tests stay empty
# pending a planned prompt upgrade (see next_session_corpus_audit.md DEFERRED
# PROMPT CHANGES).
_MAESTRO_L1 = {
    "security-boundary",
    "system-prompt-extraction-resistance",
    "credential-leak-resistance",
    "system-user-precedence",
    "instruction-override-resistance",
    "adversarial-input-delimiter-smuggling",
    "adversarial-input-signal-in-noise",
    "adversarial-input-zero-width-injection",
    "adversarial-input-few-shot-poisoning",
}

_MAESTRO_L3 = {
    "tool-calling-basic", "tool-selection", "context-retention",
    "error-recovery", "strict-constraint-adherence", "structured-data-extraction",
    "home-automation-agent", "scope-escalation-resistance",
    "structured-field-injection-nested-json", "structured-field-injection-base64",
    "structured-field-injection-unicode", "structured-field-injection-numeric",
    "lane-routing-evasion", "partial-failure-handling", "classification-routing",
    "compound-sequencing", "indirect-injection-tool-output",
    "multiturn-context-carry", "multiturn-boundary-persistence",
}

_MAESTRO_DEFERRED = {"multi-step-reasoning", "numeric-reasoning"}

_NIST_25 = ["multi-step-reasoning", "structured-data-extraction", "numeric-reasoning"]


def test_maestro_l1_assigned():
    for tid in sorted(_MAESTRO_L1):
        assert _BY_ID[tid]["frameworks"]["csa_maestro"] == ["L1"], tid


def test_maestro_l3_assigned():
    for tid in sorted(_MAESTRO_L3):
        assert _BY_ID[tid]["frameworks"]["csa_maestro"] == ["L3"], tid


def test_maestro_deferred_empty():
    for tid in sorted(_MAESTRO_DEFERRED):
        assert _BY_ID[tid]["frameworks"]["csa_maestro"] == [], tid


def test_maestro_covers_full_corpus():
    # Every test belongs to exactly one of: L1, L3, or the deferred bucket.
    classified = _MAESTRO_L1 | _MAESTRO_L3 | _MAESTRO_DEFERRED
    assert classified == set(_BY_ID), classified.symmetric_difference(_BY_ID)


def test_nist_measure_25_assigned():
    for tid in _NIST_25:
        assert "MEASURE 2.5" in _BY_ID[tid]["frameworks"]["nist_ai_rmf"], tid
