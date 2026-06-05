"""Render one corpus-catalog markdown entry from audited metadata + fixtures."""

from __future__ import annotations

from typing import Any

_FRAMEWORK_LABELS = {
    "owasp_llm_top10_2025": "OWASP LLM Top 10 (2025)",
    "mitre_atlas_v5_1": "MITRE ATLAS v5.1",
    "csa_maestro": "CSA MAESTRO",
    "nist_ai_rmf": "NIST AI RMF",
}

_FENCE = "```"


def render_entry(entry: dict[str, Any], fixtures: list[dict[str, Any]]) -> str:
    """Render a single test's catalog entry as markdown.

    'frameworks' maps framework key -> list of [control_id, rationale] pairs.
    'fixtures' supplies up to one should-pass and one should-fail representative case.
    """
    lines: list[str] = [f"## {entry['test_id']}", ""]
    lines += ["### Purpose", entry["purpose"], ""]

    lines.append("### Prompt(s)")
    if entry.get("system"):
        lines += ["**System:**", "", _FENCE, entry["system"], _FENCE, ""]
    if entry.get("turns"):
        for i, turn in enumerate(entry["turns"], 1):
            lines += [f"**Turn {i}:**", "", _FENCE, turn, _FENCE, ""]
    elif entry.get("prompt"):
        lines += ["**User:**", "", _FENCE, entry["prompt"], _FENCE, ""]

    lines += ["### Grading logic", entry["grading_logic"], ""]

    lines += ["### Framework mapping", "", "| Framework | Control | Rationale |", "|---|---|---|"]
    for fw_key, pairs in (entry.get("frameworks") or {}).items():
        label = _FRAMEWORK_LABELS.get(fw_key, fw_key)
        for pair in pairs:
            # Accept a [control_id, rationale] pair (catalog format), a bare
            # control-id string (raw dataset format), or a short/long list —
            # default the rationale to "" rather than crashing on unpack/index.
            if isinstance(pair, str):
                control_id, rationale = pair, ""
            elif isinstance(pair, (list, tuple)):
                control_id = pair[0] if len(pair) > 0 else ""
                rationale = pair[1] if len(pair) > 1 else ""
            else:
                control_id, rationale = str(pair), ""
            lines.append(f"| {label} | {control_id} | {rationale} |")
    lines.append("")

    limits = entry.get("known_limitations", [])
    if limits:
        lines += ["### Known limitations"] + [f"- {x}" for x in limits] + [""]

    passes = [f for f in fixtures if f.get("expected_verdict")]
    fails = [f for f in fixtures if not f.get("expected_verdict")]
    if passes or fails:
        lines.append("### Representative cases")
        if passes:
            lines.append(f"- **Should pass:** {passes[0]['label_rationale']}")
        if fails:
            lines.append(f"- **Should fail:** {fails[0]['label_rationale']}")
        lines.append("")

    return "\n".join(lines)
