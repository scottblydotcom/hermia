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


# --- OWASP LLM Top 10 (2025) (audited 2026-06-06, multi-mapping ≤2 codes per test) ---
# Capability tests have empty OWASP mappings (no attack surface in the prompt).
# Every security test names LLM01:2025 (prompt injection is the vector); secondary
# codes name the distinct CONSEQUENCE the test probes.
_OWASP_EMPTY = {
    "tool-calling-basic", "multi-step-reasoning", "error-recovery",
    "strict-constraint-adherence", "context-retention", "home-automation-agent",
    "structured-data-extraction", "tool-selection", "partial-failure-handling",
    "numeric-reasoning", "compound-sequencing", "multiturn-context-carry",
}

_OWASP_LLM01_ONLY = {
    "structured-field-injection-nested-json", "structured-field-injection-base64",
    "structured-field-injection-unicode", "structured-field-injection-numeric",
    "adversarial-input-delimiter-smuggling", "adversarial-input-signal-in-noise",
    "adversarial-input-zero-width-injection", "adversarial-input-few-shot-poisoning",
    "instruction-override-resistance", "classification-routing",
    "indirect-injection-tool-output", "multiturn-boundary-persistence",
}

# Secondary code per test
_OWASP_SECONDARY = {
    "security-boundary":                    "LLM06:2025",  # agency overreach
    "system-prompt-extraction-resistance":  "LLM07:2025",  # system prompt leak
    "scope-escalation-resistance":          "LLM06:2025",  # permission overreach
    "lane-routing-evasion":                 "LLM02:2025",  # credential disclosure
    "credential-leak-resistance":           "LLM02:2025",  # sensitive info disclosure
    "system-user-precedence":               "LLM06:2025",  # privilege overreach
}


def test_owasp_empty_for_capability():
    for tid in sorted(_OWASP_EMPTY):
        assert _BY_ID[tid]["frameworks"]["owasp_llm_top10"] == [], tid


def test_owasp_llm01_only_assigned():
    for tid in sorted(_OWASP_LLM01_ONLY):
        assert _BY_ID[tid]["frameworks"]["owasp_llm_top10"] == ["LLM01:2025"], tid


def test_owasp_secondary_assigned():
    for tid, secondary in sorted(_OWASP_SECONDARY.items()):
        assert _BY_ID[tid]["frameworks"]["owasp_llm_top10"] == ["LLM01:2025", secondary], tid


def test_owasp_covers_full_corpus():
    classified = _OWASP_EMPTY | _OWASP_LLM01_ONLY | set(_OWASP_SECONDARY)
    assert classified == set(_BY_ID), classified.symmetric_difference(_BY_ID)


# --- MITRE ATLAS 6.0.0 (audited 2026-06-06, multi-mapping ≤2 codes per test) ---
# Capability tests = empty. Every security test names a T0051 sub-technique
# (Direct/Indirect) — or T0056 for the system-prompt-extraction bullseye.
_ATLAS_EMPTY = {
    "tool-calling-basic", "multi-step-reasoning", "error-recovery",
    "strict-constraint-adherence", "context-retention", "home-automation-agent",
    "structured-data-extraction", "tool-selection", "partial-failure-handling",
    "numeric-reasoning", "compound-sequencing", "multiturn-context-carry",
}

# Bullseye-mapped (single specific technique, no T0051 primary)
_ATLAS_SPECIAL = {
    "system-prompt-extraction-resistance": ["AML.T0056"],
    "indirect-injection-tool-output":      ["AML.T0051.001", "AML.T0099"],
}

_ATLAS_T0051_DIRECT_ONLY = {
    "security-boundary", "scope-escalation-resistance",
    "structured-field-injection-nested-json", "structured-field-injection-numeric",
    "adversarial-input-delimiter-smuggling", "adversarial-input-signal-in-noise",
    "adversarial-input-few-shot-poisoning",
    "instruction-override-resistance", "classification-routing",
    "system-user-precedence", "multiturn-boundary-persistence",
}

# Secondary code per test (always paired with AML.T0051.000)
_ATLAS_SECONDARY = {
    "structured-field-injection-base64":        "AML.T0068",  # obfuscation
    "structured-field-injection-unicode":       "AML.T0068",  # obfuscation
    "adversarial-input-zero-width-injection":   "AML.T0068",  # obfuscation
    "lane-routing-evasion":                     "AML.T0057",  # data leakage
    "credential-leak-resistance":               "AML.T0057",  # data leakage
}


def test_atlas_empty_for_capability():
    for tid in sorted(_ATLAS_EMPTY):
        assert _BY_ID[tid]["frameworks"]["mitre_atlas"] == [], tid


def test_atlas_t0051_direct_only_assigned():
    for tid in sorted(_ATLAS_T0051_DIRECT_ONLY):
        assert _BY_ID[tid]["frameworks"]["mitre_atlas"] == ["AML.T0051.000"], tid


def test_atlas_secondary_assigned():
    for tid, secondary in sorted(_ATLAS_SECONDARY.items()):
        assert _BY_ID[tid]["frameworks"]["mitre_atlas"] == ["AML.T0051.000", secondary], tid


def test_atlas_special_assigned():
    for tid, expected in sorted(_ATLAS_SPECIAL.items()):
        assert _BY_ID[tid]["frameworks"]["mitre_atlas"] == expected, tid


def test_atlas_covers_full_corpus():
    classified = (
        _ATLAS_EMPTY | _ATLAS_T0051_DIRECT_ONLY
        | set(_ATLAS_SECONDARY) | set(_ATLAS_SPECIAL)
    )
    assert classified == set(_BY_ID), classified.symmetric_difference(_BY_ID)
