"""Hermia EvalApp — entry point."""

import argparse
import sys

from textual.app import App

import hermia.runner as runner
from hermia.metrics import detect_gpu
from hermia.runner import get_available_models
from hermia.screens import SelectionScreen


class EvalApp(App):  # type: ignore[type-arg]
    TITLE = "Hermia LLM Eval"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, fleet_mode: bool = False, repeat: int = 1) -> None:
        super().__init__()
        self.fleet_mode = fleet_mode
        self.repeat = repeat
        self.model_list = get_available_models()
        self.gpu_info = detect_gpu()

    def on_mount(self) -> None:
        self.push_screen(SelectionScreen(repeat=self.repeat))


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermia LLM Eval")
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="Run each (model, test) pair N times (default: 1)",
    )
    args = parser.parse_args()

    if args.repeat < 1:
        print("error: --repeat N must be >= 1", file=sys.stderr)
        sys.exit(2)

    runner.OLLAMA_BASE = args.host.rstrip("/")
    fleet_mode = "localhost" not in args.host and "127.0.0.1" not in args.host

    EvalApp(fleet_mode=fleet_mode, repeat=args.repeat).run()


if __name__ == "__main__":
    main()
