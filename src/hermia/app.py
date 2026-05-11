"""Hermia EvalApp — entry point."""

import argparse

from textual.app import App

import hermia.runner as runner
from hermia.metrics import detect_gpu
from hermia.runner import get_available_models
from hermia.screens import SelectionScreen


class EvalApp(App):  # type: ignore[type-arg]
    TITLE = "Hermia LLM Eval"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, fleet_mode: bool = False) -> None:
        super().__init__()
        self.fleet_mode = fleet_mode
        self.model_list = get_available_models()
        self.gpu_info = detect_gpu()

    def on_mount(self) -> None:
        self.push_screen(SelectionScreen())


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermia LLM Eval")
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    args = parser.parse_args()

    runner.OLLAMA_BASE = args.host.rstrip("/")
    fleet_mode = "localhost" not in args.host and "127.0.0.1" not in args.host

    EvalApp(fleet_mode=fleet_mode).run()


if __name__ == "__main__":
    main()
