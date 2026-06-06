"""Tripwire for CSA MAESTRO + NIST AI RMF mappings in the runtime dataset.

MAESTRO single-layer mapping audited 2026-06-06 against the official CSA paper
(Huang 2025); see docs/maestro-reference.md.

NIST AI RMF single-subcategory mapping audited 2026-06-06 against NIST AI 100-1
(Jan 2023) and the AI RMF Playbook; see docs/nist-ai-rmf-reference.md.
"""
from hermia.runner import load_tests_all

_BY_ID = {t["id"]: t for t in load_tests_all()}

# --- CSA MAESTRO (audited 2026-06-06, single layer per test) ---
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
    classified = _MAESTRO_L1 | _MAESTRO_L3 | _MAESTRO_DEFERRED
    assert classified == set(_BY_ID), classified.symmetric_difference(_BY_ID)


# --- NIST AI RMF (audited 2026-06-06, single subcategory per test) ---
_NIST_M25 = {
    # Valid & Reliable — all capability tests
    "tool-calling-basic", "multi-step-reasoning", "error-recovery",
    "strict-constraint-adherence", "context-retention", "home-automation-agent",
    "structured-data-extraction", "tool-selection", "partial-failure-handling",
    "numeric-reasoning", "compound-sequencing", "multiturn-context-carry",
}

_NIST_M27 = {
    # Security & Resilience — all security tests
    "security-boundary", "system-prompt-extraction-resistance",
    "scope-escalation-resistance",
    "structured-field-injection-nested-json", "structured-field-injection-base64",
    "structured-field-injection-unicode", "structured-field-injection-numeric",
    "adversarial-input-delimiter-smuggling", "adversarial-input-signal-in-noise",
    "adversarial-input-zero-width-injection", "adversarial-input-few-shot-poisoning",
    "lane-routing-evasion", "instruction-override-resistance",
    "classification-routing", "indirect-injection-tool-output",
    "credential-leak-resistance", "system-user-precedence",
    "multiturn-boundary-persistence",
}


def test_nist_measure_25_assigned():
    for tid in sorted(_NIST_M25):
        assert _BY_ID[tid]["frameworks"]["nist_ai_rmf"] == ["MEASURE 2.5"], tid


def test_nist_measure_27_assigned():
    for tid in sorted(_NIST_M27):
        assert _BY_ID[tid]["frameworks"]["nist_ai_rmf"] == ["MEASURE 2.7"], tid


def test_nist_covers_full_corpus():
    classified = _NIST_M25 | _NIST_M27
    assert classified == set(_BY_ID), classified.symmetric_difference(_BY_ID)
