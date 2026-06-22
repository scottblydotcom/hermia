# TUI Footer & Header Design

**Date:** 2026-06-22
**Status:** Approved

## Goal

Add Textual's built-in `Footer` widget to all non-modal TUI screens so key bindings are
visible to the user. Header treatment is exploratory and will be decided during implementation
by running the app.

## Footer

Use Textual's built-in `Footer` widget. No custom code — it auto-renders all `show=True`
BINDINGS for the active screen.

**Scope:** All 8 non-modal screens. Modals (`FleetNameModal`, `AddHostModal`) are excluded.

**Implementation:** Add `from textual.widgets import Footer` to each screen file's imports
and `yield Footer()` as the last item in each `compose()` method.

### Expected footer content per screen

| Screen | Key hints shown |
|--------|----------------|
| `LaunchScreen` | `↵ Select`, `Q Quit` (`Esc Back` is `show=False` — intentional, no back from root) |
| `FleetConfigScreen` | `Esc Back`, `↵ Drill`, `S Save` |
| `HostsScreen` | `Esc Back`, `+ Add host`, `↵ Models` |
| `HostModelsScreen` | `Esc Back`, `Space Toggle`, `A All`, `N None` |
| `TestsScreen` | `Esc Back`, `Space Toggle`, `A All`, `N None` |
| `RunnerScreen` | `Esc Back`, `↵ Trials` |
| `RunnerTrialsScreen` | `Esc Back`, `↵ Detail` |
| `RunnerDetailScreen` | `Esc Back` |

## Header

All screens already yield a `Breadcrumb` widget as their first composed element, which
serves as the contextual header (showing the navigation path). Whether to add Textual's
`Header()` widget above the Breadcrumb will be decided by running the app after footers
are in place. If it adds value, apply it; if it duplicates or crowds the Breadcrumb, skip it.

## Testing

Existing tests cover `compose()` structure. After adding `Footer()`, verify:
- `pytest` still passes (no regressions)
- App boots and footers are visible on all 8 screens (manual run via `hermia --fleet`)
