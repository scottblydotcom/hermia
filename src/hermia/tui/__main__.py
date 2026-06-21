"""`python -m hermia.tui` — launches the unified Fleet TUI.

Separate from the existing `hermia` CLI (src/hermia/app.py:main) during
Plan 2 development. Plan 4 rewires the main entry to point here and deletes
src/hermia/screens.py.
"""
from hermia.tui.app import HermiaApp


def main() -> None:
    HermiaApp().run()


if __name__ == "__main__":
    main()
