"""HermiaApp — Textual App for the unified Fleet TUI.

Holds the shared FleetConfig as a mutable attribute. Picker screens read
and write directly to `app.config`. `app.bus` is the shared SessionBus for
runner ↔ screen communication (probe topics and run topics share one bus;
they use distinct topic prefixes and screens only subscribe to their own).
"""
from __future__ import annotations

import sys

from textual.app import App

from hermia.tui.bus import SessionBus
from hermia.tui.state import FleetConfig


class HermiaApp(App[None]):
    CSS_PATH = None  # widgets define their own DEFAULT_CSS

    def __init__(self, engine_security_host: str | None = None) -> None:
        super().__init__()
        self.config: FleetConfig = FleetConfig(name="")
        self.bus: SessionBus = SessionBus()
        # Local Ollama host to probe for engine-security advisories after
        # mount (see _probe_engine_security). None disables the probe
        # (e.g. for tests that don't want a network call at startup).
        self._engine_security_host: str | None = engine_security_host

    def on_mount(self) -> None:
        # Import here to avoid a circular import — screens.launch imports HermiaApp.
        from hermia.tui.screens.launch import LaunchScreen
        self.push_screen(LaunchScreen())
        if self._engine_security_host is not None:
            # Off-thread: check_ollama_security does a synchronous
            # requests.get with a 3-second timeout — blocking on_mount would
            # stall the TUI's first paint by that long when the Ollama host
            # is unreachable.
            self.run_worker(
                self._probe_engine_security,
                thread=True,
                exclusive=True,
                name="engine-security",
            )

    def _probe_engine_security(self) -> None:
        """Run the engine-security check off the main thread.

        Emits any warnings both to stderr (for redirected-fd logging) and
        as in-app toast notifications via ``call_from_thread``, since
        Textual's message pump lives on the main thread.
        """
        from hermia.preflight import check_engine_security
        host = self._engine_security_host
        if host is None:
            return
        # Advisory-only: never let a malformed /api/version response or
        # unexpected transport error kill the worker and lose the toast.
        try:
            warnings = check_engine_security(host, "ollama", fleet_mode=False)
        except Exception as exc:  # noqa: BLE001 — advisory-only, degrade quietly
            warnings = [f"SEC ⚠ engine-security probe failed: {exc}"]
        # Skip stderr on a live TTY — Textual owns the terminal in raw mode
        # and a bare write would corrupt the rendered UI. The toast still
        # surfaces the warning interactively; redirected-fd invocations
        # (`hermia 2>log`) still capture it. sys.stderr can be None under
        # GUI wrappers / daemonized launchers.
        # Custom stream shims (some test runners, GUI wrappers) may not
        # implement isatty(); treat "no isatty" as safe to write (same
        # semantics as a non-TTY file).
        isatty = getattr(sys.stderr, "isatty", None)
        stderr_safe = (
            sys.stderr is not None
            and (isatty is None or not isatty())
        )
        for w in warnings:
            if stderr_safe:
                try:
                    print(w, file=sys.stderr)
                except (OSError, ValueError, AttributeError):
                    # stderr closed / detached under us; the toast still
                    # surfaces the warning, so drop the log line silently.
                    pass
            try:
                self.call_from_thread(
                    self.notify, w, severity="warning", timeout=15
                )
            except RuntimeError:
                # App unmounted / event loop closed while the probe was
                # still running (worst case: within the 3s /api/version
                # window). Losing the toast on shutdown is fine — the
                # stderr line above already captured it for logging.
                return

    def on_unmount(self) -> None:
        self.bus.close()
