"""Hermia EvalApp — entry point."""

from textual.app import App

from hermia.runner import get_available_models
from hermia.screens import SelectionScreen


class EvalApp(App):  # type: ignore[type-arg]
    TITLE = "Hermia LLM Eval"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.model_list = get_available_models()

    def on_mount(self) -> None:
        self.push_screen(SelectionScreen())


def main() -> None:
    EvalApp().run()


if __name__ == "__main__":
    main()
