"""Tests for hermia.tui.test_catalog — TestRecord + load_test_catalog()."""
from hermia.tui.test_catalog import FRAMEWORKS, TestRecord, load_test_catalog


class TestLoadTestCatalog:
    def test_returns_one_record_per_test_id(self) -> None:
        from hermia.schemas import TEST_IDS
        catalog = load_test_catalog()
        assert {r.id for r in catalog} == set(TEST_IDS)

    def test_records_have_frameworks_keys(self) -> None:
        catalog = load_test_catalog()
        for r in catalog:
            assert set(r.frameworks.keys()) == set(FRAMEWORKS)
            for v in r.frameworks.values():
                assert isinstance(v, bool)

    def test_known_test_has_expected_framework_membership(self) -> None:
        catalog = load_test_catalog()
        # security-boundary is in agentic-tasks.json with non-empty csa_maestro.
        rec = next(r for r in catalog if r.id == "security-boundary")
        # At least one framework membership should be True for an annotated test.
        assert any(rec.frameworks.values())


class TestTestRecord:
    def test_is_in_framework_helper(self) -> None:
        rec = TestRecord(
            id="x",
            frameworks={"OWASP": True, "ATLAS": False, "MAESTRO": True, "NIST": False},
        )
        assert rec.is_in_framework("OWASP") is True
        assert rec.is_in_framework("ATLAS") is False
