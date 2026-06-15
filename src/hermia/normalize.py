"""Output normalization shared by the grader and reproducibility scoring.

`strip_fences` MUST stay the single source of truth: the eval grader uses it
to extract JSON before checking schema, and reproducibility scoring uses it to
compute canonical-output equality. They must apply the identical transform or
`exact_match_rate_canonical` would diverge from what the grader actually saw.
"""

import re


def strip_fences(text: str) -> str:
    """Extract content from markdown code fences, ignoring surrounding prose."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text
