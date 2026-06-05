import pytest

from hermia.corpus_audit.assembler import assemble_catalog


def test_assemble_concatenates_scoring_then_entries():
    md = assemble_catalog("## Scoring\nrollup prose", ["## a\nx", "## b\ny"], expected_count=2)
    assert md.index("## Scoring") < md.index("## a") < md.index("## b")


def test_assemble_rejects_short_count():
    with pytest.raises(ValueError, match="expected 30"):
        assemble_catalog("s", ["## only-one"], expected_count=30)
