"""Hermia EvalApp — entry point."""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from textual.app import App

from hermia import __version__
from hermia.metrics import detect_gpu
from hermia.runner import detect_mode, get_available_models
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


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"N must be >= 1, got {value}")
    return ivalue


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermia LLM Eval")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--repeat",
        type=_positive_int,
        default=1,
        metavar="N",
        help="Run each (model, test) pair N times (default: 1)",
    )
    parser.add_argument(
        "--fleet",
        metavar="FILE",
        help="YAML fleet config; runs headless eval against all hosts and exits",
    )
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose fleet output: show t/s and failure reason per test",
    )
    verbosity_group.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet fleet output: suppress progress, print only saved path on completion",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Max number of distinct hosts evaluated concurrently (default: 4)",
    )
    parser.add_argument(
        "--audit",
        nargs="?",
        const=True,
        metavar="FILE",
        help="Print audit report from FILE (or all results/) and exit",
    )
    parser.add_argument(
        "--audit-format",
        choices=["jsonl", "html", "spill"],
        default="jsonl",
        dest="audit_format",
        help="Audit output format: jsonl (default), html, or spill (fleet health table)",
    )
    submit_group = parser.add_mutually_exclusive_group()
    submit_group.add_argument(
        "--submit",
        action="store_true",
        help=(
            "After a fleet run, anonymize results and POST to HERMIA_SUBMIT_URL "
            "(opt-in community submission; nothing is sent without this flag)"
        ),
    )
    submit_group.add_argument(
        "--submit-dry-run",
        action="store_true",
        dest="submit_dry_run",
        help="Print the anonymized submission payload without sending it",
    )
    args = parser.parse_args()

    if (args.verbose or args.quiet) and not args.fleet:
        parser.error("--verbose and --quiet can only be used with --fleet")

    if args.audit is not None:
        from hermia.audit import run_audit
        from hermia.screens import RESULTS_DIR

        source = RESULTS_DIR if args.audit is True else Path(args.audit)
        if not source.exists():
            print(f"hermia: audit source not found: {source}", file=sys.stderr)
            sys.exit(1)
        out_file: Path | None = None
        if args.audit_format == "html" and sys.stdout.isatty():
            out_file = Path(f"hermia-audit-{date.today().isoformat()}.html")
            print(f"hermia: writing report to {out_file}", file=sys.stderr)
        run_audit(source, fmt=args.audit_format, output=out_file)
        sys.exit(0)

    if args.fleet:
        from hermia.fleet import load_fleet_config, run_fleet
        from hermia.results import load_jsonl
        from hermia.screens import RESULTS_DIR
        from hermia.sink.submission import SubmissionSink

        verbosity = 1 if args.verbose else (-1 if args.quiet else 0)
        try:
            entries = load_fleet_config(Path(args.fleet))
            jsonl_path = run_fleet(
                entries,
                repeat=args.repeat,
                results_dir=RESULTS_DIR,
                verbosity=verbosity,
                max_concurrency=args.max_concurrency,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"hermia: {exc}", file=sys.stderr)
            sys.exit(1)

        if args.submit_dry_run:
            SubmissionSink(endpoint=None, dry_run=True).write(load_jsonl(jsonl_path))
        elif args.submit:
            SubmissionSink(
                endpoint=os.environ.get("HERMIA_SUBMIT_URL"),
                token_env="HERMIA_SUBMIT_TOKEN",  # noqa: S106
                dry_run=False,
            ).write(load_jsonl(jsonl_path))

        sys.exit(0)

    os.environ["HERMIA_HOST"] = args.host.rstrip("/")
    fleet_mode = detect_mode(args.host) == "fleet"

    EvalApp(fleet_mode=fleet_mode, repeat=args.repeat).run()


if __name__ == "__main__":
    main()
