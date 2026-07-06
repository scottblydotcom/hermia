"""Corpus-hash provenance stamping — hermia-khq.

Every result row carries ``corpus_sha256`` (the SHA-256 of the shipped
``agentic-tasks.json``) so a row can be tied to the exact corpus that produced
it without git archaeology, and corpus drift becomes self-evident. This is the
row-level half of the roadmap's Track 1 provenance promise
("hermia_version + corpus-hash stamping on every row"); the human-readable
``corpus_version`` string is the complementary label.
"""

import hashlib

from hermia.export import _PG_COLUMNS
from hermia.runner import PACKAGE_DIR, corpus_sha256
from hermia.sink.anonymize import anonymize_row

_CORPUS_PATH = PACKAGE_DIR / "test-datasets" / "agentic-tasks.json"


def test_corpus_sha256_is_64_char_lowercase_hex():
    h = corpus_sha256()
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_corpus_sha256_matches_raw_file_bytes():
    expected = hashlib.sha256(_CORPUS_PATH.read_bytes()).hexdigest()
    assert corpus_sha256() == expected


def test_corpus_sha256_is_stable_across_calls():
    # Module-cached: two calls must return the identical value.
    assert corpus_sha256() == corpus_sha256()


def test_corpus_sha256_survives_anonymization():
    # Provenance must reach the community dataset — the anonymizer is an
    # allowlist, so a non-allowlisted field would be silently dropped.
    sentinel = "ab12cd34" * 8  # 64-char stand-in hash
    row = {
        "test_id": "credential-leak-resistance",
        "model": "m",
        "corpus_sha256": sentinel,
        "host": "secret-internal-host",  # must NOT survive
    }
    out = anonymize_row(row)
    assert out.get("corpus_sha256") == sentinel
    assert "host" not in out  # sanity: allowlist still default-denies


def test_corpus_sha256_is_a_persisted_pg_column():
    # Guards the export wiring so a row's provenance reaches Postgres.
    assert "corpus_sha256" in _PG_COLUMNS
