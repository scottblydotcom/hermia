"""Tests for the VRAM sanity-bound cross-check (hermia-cfqv wiring)."""
from hermia.identity.vram_check import vram_sanity_check


def test_ok_when_total_vram_exceeds_model_footprint():
    assert vram_sanity_check(32 * 1024**3, 20.0) == "ok"


def test_mismatch_when_model_needs_more_than_box_has():
    assert vram_sanity_check(24 * 1024**3, 70.0) == "mismatch"


def test_unchecked_when_probe_has_no_vram():
    assert vram_sanity_check(None, 20.0) == "unchecked"


def test_unchecked_when_endpoint_reports_no_size_vram():
    assert vram_sanity_check(32 * 1024**3, None) == "unchecked"


def test_small_slack_band_tolerates_measurement_noise():
    assert vram_sanity_check(32 * 1024**3, 32.2) == "ok"
