"""Tests for StatusBadge — ✓ ↺ ✗ ! glyphs with direction-aware color."""
from hermia.tui.widgets.status_badge import (
    ICONS,
    StatusBadge,
    color_for,
)


class TestColorFor:
    def test_defended_is_green(self) -> None:
        assert color_for("defended") == "green"

    def test_breached_is_red(self) -> None:
        assert color_for("breached") == "red"

    def test_error_is_yellow(self) -> None:
        assert color_for("error") == "yellow"

    def test_refused_on_harmful_test_is_green(self) -> None:
        assert color_for("refused", direction="harmful") == "green"

    def test_refused_on_benign_test_is_red(self) -> None:
        assert color_for("refused", direction="benign") == "red"

    def test_refused_default_direction_is_harmful(self) -> None:
        assert color_for("refused") == "green"


class TestIcons:
    def test_all_four_statuses_have_icons(self) -> None:
        assert ICONS["defended"] == "✓"
        assert ICONS["refused"] == "↺"
        assert ICONS["breached"] == "✗"
        assert ICONS["error"] == "!"


class TestStatusBadge:
    def test_renders_defended(self) -> None:
        badge = StatusBadge("defended")
        text = badge.markup
        assert "✓" in text
        assert "green" in text

    def test_renders_breached(self) -> None:
        badge = StatusBadge("breached")
        text = badge.markup
        assert "✗" in text
        assert "red" in text

    def test_renders_refused_harmful(self) -> None:
        badge = StatusBadge("refused", direction="harmful")
        text = badge.markup
        assert "↺" in text
        assert "green" in text

    def test_renders_refused_benign(self) -> None:
        badge = StatusBadge("refused", direction="benign")
        text = badge.markup
        assert "↺" in text
        assert "red" in text

    def test_update_status_changes_render(self) -> None:
        badge = StatusBadge("defended")
        badge.update_status("breached")
        text = badge.markup
        assert "✗" in text
        assert "red" in text

    def test_update_status_can_change_direction(self) -> None:
        badge = StatusBadge("refused", direction="harmful")
        badge.update_status("refused", direction="benign")
        assert badge.direction == "benign"
        text = badge.markup
        assert "red" in text
