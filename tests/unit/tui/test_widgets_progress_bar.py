"""Tests for progress widgets — MiniProgressBar (per-host) and AggregateProgressBar."""
from hermia.tui.widgets.progress_bar import (
    AggregateProgressBar,
    MiniProgressBar,
)


class TestMiniProgressBar:
    def test_initial_state(self) -> None:
        bar = MiniProgressBar(total=100)
        assert bar.total == 100
        assert bar.completed == 0
        # Empty progress: zero filled blocks.
        assert "█" not in bar.text

    def test_partial_progress(self) -> None:
        bar = MiniProgressBar(total=10, width=20)
        bar.advance(5)
        assert bar.completed == 5
        # 50% of width=20 should be filled.
        assert bar.text.count("█") == 10

    def test_full_progress(self) -> None:
        bar = MiniProgressBar(total=10, width=20)
        bar.advance(10)
        assert bar.text.count("█") == 20

    def test_advance_clips_at_total(self) -> None:
        bar = MiniProgressBar(total=10)
        bar.advance(15)
        assert bar.completed == 10

    def test_set_total_renormalizes(self) -> None:
        bar = MiniProgressBar(total=10, width=20)
        bar.advance(5)
        bar.set_total(20)  # was 50% complete; now 25%
        assert bar.text.count("█") == 5  # 25% of 20

    def test_zero_total_does_not_crash(self) -> None:
        bar = MiniProgressBar(total=0)
        assert "█" not in bar.text


class TestAggregateProgressBar:
    def test_initial_state(self) -> None:
        bar = AggregateProgressBar(total=564)
        assert bar.total == 564
        assert bar.completed == 0
        assert "0 / 564" in bar.text

    def test_advance_updates_count_and_percent(self) -> None:
        bar = AggregateProgressBar(total=100)
        bar.advance(25)
        assert "25 / 100" in bar.text
        assert "25%" in bar.text

    def test_zero_total_does_not_crash(self) -> None:
        bar = AggregateProgressBar(total=0)
        assert "0 / 0" in bar.text
        assert "%" in bar.text
