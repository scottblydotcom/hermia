# hermia-bo1 — Ollama security posture checks (v1)

## What this bead does

Hermia is a security evaluation tool. It should surface known Ollama security
issues at run time, not silently evaluate against a vulnerable server. This is
the first iteration of an ongoing security-check subsystem (hermia-co9 tracks
the backlog).

## v1 scope — two checks

### Check 1: CVE-2026-7482 version gate (CVSS 9.1, "Bleeding Llama")
- Fixed in Ollama 0.17.1
- Attack: unauthenticated POST to `/api/create` with crafted GGUF → heap OOB
  read → exfiltrates env vars, API keys, system prompts, peer session data via
  `/api/push`
- Action: query `/api/version`, warn if version < 0.17.1
- Warning text: `SEC ⚠ CVE-2026-7482 (CVSS 9.1): Ollama {ver} is vulnerable
  to heap memory disclosure — upgrade to 0.17.1+`

### Check 2: CVE-2026-5757 advisory (no patch)
- No fixed version — architectural issue in GGUF model loader
- Same attack class as 7482 (crafted GGUF → heap leak) but no upstream fix
- Action: always emit advisory if Ollama is reachable and running in local mode
  (fleet mode may have auth; local mode is the exposed case)
- Warning text: `SEC ⚠ CVE-2026-5757 (no patch): Ollama model upload endpoint
  is unpatched — restrict /api/create to localhost or trusted networks`

Both warnings are surfaced in the TUI run log alongside existing preflight
output. In fleet mode, Check 2 is omitted (assume operator controls access).

## Changes

### `src/hermia/preflight.py`

Add constant:
```python
OLLAMA_MIN_SECURE_VERSION = "0.17.1"
```

Add function:
```python
def check_ollama_security(host: str, fleet_mode: bool = False) -> list[str]:
    """Query /api/version and return security warning strings. Never raises."""
    ...
```

Returns a list of zero or more warning strings (empty = no issues found).

Version check logic:
```python
def _parse_version(v: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' → (X, Y, Z). Returns (0,) on parse failure."""
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except (ValueError, AttributeError):
        return (0,)

def _min_secure() -> tuple[int, ...]:
    return _parse_version(OLLAMA_MIN_SECURE_VERSION)
```

Implementation:
```python
def check_ollama_security(host: str, fleet_mode: bool = False) -> list[str]:
    import requests
    warnings: list[str] = []
    try:
        resp = requests.get(f"{host}/api/version", timeout=3)
        if resp.ok:
            ver = resp.json().get("version", "")
            if ver and _parse_version(ver) < _min_secure():
                warnings.append(
                    f"SEC ⚠ CVE-2026-7482 (CVSS 9.1): Ollama {ver} is vulnerable "
                    f"to heap memory disclosure — upgrade to {OLLAMA_MIN_SECURE_VERSION}+"
                )
    except Exception:  # noqa: BLE001
        pass  # offline or non-Ollama endpoint — skip silently

    if not fleet_mode:
        warnings.append(
            "SEC ⚠ CVE-2026-5757 (no patch): Ollama model upload endpoint is "
            "unpatched — restrict /api/create to localhost or trusted networks"
        )
    return warnings
```

Add `security_warnings: list[str]` field to `PreflightReport`:
```python
@dataclass
class PreflightReport:
    ...
    security_warnings: list[str] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        # existing model/disk warnings unchanged
        ...
```

Note: `security_warnings` is a separate field, NOT merged into `warnings`.
`screens.py` handles them separately so they can be styled distinctly.

Update `run_preflight()`:
```python
def run_preflight(...) -> PreflightReport:
    ...
    host = _normalize_host(os.environ.get("HERMIA_HOST", "http://localhost:11434"))
    sec = check_ollama_security(host, fleet_mode=fleet_mode)
    return PreflightReport(
        ...,
        security_warnings=sec,
    )
```

Import `os` at top of `preflight.py`. Add a small helper:
```python
def _normalize_host(host: str) -> str:
    host = host.rstrip("/")
    return host if "://" in host else f"http://{host}"
```
(Do NOT import from `runner.py` — avoid circular dependency.)

### `src/hermia/screens.py`

After the existing `for w in pf.warnings:` block (~line 283), add:
```python
for sw in pf.security_warnings:
    append_log(f"  {sw}", "warn")
```

### `README.md`

Add a `## Security` section after the existing feature list, before the
Getting Started link. Content:

```markdown
## Security

Hermia communicates with Ollama over HTTP/HTTPS and never uploads model files.
It is not affected by model-upload CVEs (CVE-2026-7482, CVE-2026-5757).

**Protect your Ollama instance:**
- Run Ollama bound to `127.0.0.1` (default) or behind a firewall — never
  expose port 11434 publicly
- Keep Ollama upgraded; 0.17.1+ patches CVE-2026-7482 (CVSS 9.1, heap memory
  disclosure via crafted model upload)
- CVE-2026-5757 (heap OOB read, no upstream patch as of May 2026) — restrict
  `/api/create` access at the network layer
- Fleet deployments: use `hermia-fleet.yaml` auth blocks or a Tailscale overlay
  to prevent unauthenticated access to remote Ollama endpoints

Hermia surfaces known version-level vulnerabilities at run time in the preflight
log as `SEC ⚠` warnings.
```

## Permitted scope

- `src/hermia/preflight.py`
- `src/hermia/screens.py`
- `README.md`
- `tests/unit/test_preflight.py`

## Acceptance criteria

1. `check_ollama_security()` returns CVE-2026-7482 warning when version < 0.17.1
2. No CVE-2026-7482 warning when version >= 0.17.1
3. CVE-2026-5757 advisory always appears in local mode; absent in fleet mode
4. Version parse failure (non-Ollama endpoint, offline) → silently returns []
   (or just the CVE-2026-5757 advisory in local mode — no crash, no CVE-7482 warning)
5. `PreflightReport.security_warnings` populated from `run_preflight()`
6. TUI displays `SEC ⚠` lines in warn style
7. README Security section present
8. Unit tests:
   - `test_ollama_security_vulnerable_version` — mock `/api/version` → "0.16.0" → CVE-7482 warning present
   - `test_ollama_security_patched_version` — mock → "0.17.1" → no CVE-7482 warning
   - `test_ollama_security_newer_version` — mock → "0.22.1" → no CVE-7482 warning
   - `test_ollama_security_version_unreachable` — requests raises → returns list with only CVE-5757 advisory (local mode)
   - `test_ollama_security_fleet_mode_no_5757` — fleet_mode=True → CVE-5757 advisory absent
   - `test_preflight_report_security_warnings_populated` — `run_preflight()` calls `check_ollama_security()`

## Estimate

0.5 days

## Why

Hermia is a security evaluation tool. Running it against a CVE-vulnerable Ollama
and not saying anything would be a credibility problem. The `SEC ⚠` prefix
establishes a convention for the hermia-co9 backlog (bind address check, model
provenance, auth enforcement) to follow.
