"""Release gate: every Tier-A (security) test's policy must be signed off by Scott."""
import json
from pathlib import Path

_META_DIR = Path(__file__).resolve().parents[3] / "catalog-meta"

_TIER_A = {
    "security-boundary", "system-prompt-extraction-resistance", "scope-escalation-resistance",
    "structured-field-injection-nested-json", "structured-field-injection-base64",
    "structured-field-injection-unicode", "structured-field-injection-numeric",
    "adversarial-input-delimiter-smuggling", "adversarial-input-signal-in-noise",
    "adversarial-input-zero-width-injection", "adversarial-input-few-shot-poisoning",
    "instruction-override-resistance", "indirect-injection-tool-output",
    "credential-leak-resistance", "system-user-precedence",
    "lane-routing-evasion", "classification-routing", "multiturn-boundary-persistence",
}


def test_all_security_policies_signed_off():
    missing = []
    for tid in sorted(_TIER_A):
        p = _META_DIR / f"{tid}.json"
        if not p.exists() or not json.loads(p.read_text())["policy_signed_off"]:
            missing.append(tid)
    assert not missing, f"unsigned security policies: {missing}"
