"""`python -m hermia.tui` — launches the unified Fleet TUI."""
from hermia.tui.app import HermiaApp


def main() -> None:
    HermiaApp().run()


if __name__ == "__main__":
    main()
