"""Where the TUI sends its results (hermia-u1v7).

Two defects lived in one branch in FleetConfigScreen.action_run:

  * results went to a per-fleet subdirectory, which no consumer scans; and
  * an UNNAMED fleet got results_dir=None, so the run executed normally and
    every row was discarded in silence.

Both are decided by `results_dir_for`, which is a pure function so it can be
asserted directly rather than by driving the screen.
"""
from pathlib import Path

from hermia.tui.screens.config import results_dir_for
from hermia.tui.state import FleetConfig


class TestResultsDirFor:
    def test_named_fleet_writes_to_the_top_level_results_dir(self) -> None:
        assert results_dir_for(FleetConfig(name="quick-local")) == Path("results")

    def test_unnamed_fleet_still_gets_a_results_dir(self) -> None:
        """Previously None — the run happened and every row was silently dropped."""
        assert results_dir_for(FleetConfig(name="")) == Path("results")

    def test_no_per_fleet_subdirectory(self) -> None:
        """A subdir is invisible to hermia-push / hermia-submit / hermia --audit."""
        got = results_dir_for(FleetConfig(name="my-fleet"))
        assert got == Path("results")
        assert "my-fleet" not in got.parts

    def test_traversal_in_a_fleet_name_cannot_escape_results(self) -> None:
        """The old code sanitised the name because it became a path segment.

        The name is no longer used in the path at all, so a hostile name from
        YAML cannot influence where results are written. Pin that.
        """
        for hostile in ("../../etc", "/absolute/evil", "..", "a/b/c"):
            assert results_dir_for(FleetConfig(name=hostile)) == Path("results")
