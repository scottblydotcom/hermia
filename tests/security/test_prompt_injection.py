"""Verify that test definitions in agentic-tasks.json cannot inject prompts."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
TASKS_FILE = PROJECT_ROOT / "test-datasets" / "agentic-tasks.json"

INJECTION_PATTERNS = [
    "ignore previous",
    "ignore all previous",
    "disregard",
    "system prompt",
    "you are now",
    "act as",
    "jailbreak",
    "do anything now",
]


def _load_tasks() -> list[dict]:
    with open(TASKS_FILE) as f:
        return json.load(f)["agentic_test_cases"]


SECURITY_TEST_IDS = {
    "system-prompt-extraction-resistance",
    "scope-escalation-resistance",
    "security-boundary",
    "structured-field-injection-nested-json",
    "structured-field-injection-base64",
    "structured-field-injection-unicode",
    "structured-field-injection-numeric",
    "adversarial-input-delimiter-smuggling",
    "adversarial-input-signal-in-noise",
    "adversarial-input-zero-width-injection",
    "adversarial-input-few-shot-poisoning",
    # v0.1.1 additions — intentionally embed adversarial patterns in user turn
    "instruction-override-resistance",  # prompt contains "system prompt" as injection attempt
    "indirect-injection-tool-output",   # tool output contains "ignore previous" / "you are now"
}


def test_no_injection_in_prompts():
    for task in _load_tasks():
        if task.get("id") in SECURITY_TEST_IDS:
            continue  # security tests intentionally contain adversarial patterns
        text = (task.get("prompt", "") + " " + task.get("system", "")).lower()
        for pattern in INJECTION_PATTERNS:
            assert pattern not in text, (
                f"Potential injection '{pattern}' found in task '{task['id']}'"
            )


def test_all_tasks_have_required_fields():
    for task in _load_tasks():
        assert "id" in task, "Task missing 'id'"
        assert "system" in task, f"Task '{task['id']}' missing 'system'"
        assert "prompt" in task, f"Task '{task['id']}' missing 'prompt'"


def test_no_shell_metacharacters_in_prompts():
    dangerous = ["`", "$(", "${", "&&", "||", "; rm", "; curl"]
    for task in _load_tasks():
        text = task.get("prompt", "") + task.get("system", "")
        for meta in dangerous:
            assert meta not in text, (
                f"Shell metachar '{meta}' found in task '{task['id']}'"
            )
