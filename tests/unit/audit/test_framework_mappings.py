from hermia.runner import load_tests_all

_BY_ID = {t["id"]: t for t in load_tests_all()}

_MAESTRO_L4 = ["tool-calling-basic", "tool-selection", "context-retention"]
_NIST_25 = ["multi-step-reasoning", "structured-data-extraction", "numeric-reasoning"]


def test_maestro_l4_assigned():
    for tid in _MAESTRO_L4:
        assert _BY_ID[tid]["frameworks"]["csa_maestro"] == ["L4"], tid


def test_nist_measure_25_assigned():
    for tid in _NIST_25:
        assert "MEASURE 2.5" in _BY_ID[tid]["frameworks"]["nist_ai_rmf"], tid
