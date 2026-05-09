# Security Policy

## Supported Versions

Hermia is pre-release software under active development. Security fixes are applied
to the current `main` branch only.

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ |
| Older commits | ❌ |

---

## Reporting a Vulnerability

Hermia is a security evaluation tool. We take vulnerability reports seriously —
probably more seriously than most projects, given what this thing does.

**Please do not report security vulnerabilities via GitHub Issues.** Public issue
disclosure gives attackers a head start.

Instead, report privately via one of the following:

- **GitHub Private Vulnerability Reporting** — use the
  [Report a vulnerability](https://github.com/scottblydotcom/hermia/security/advisories/new)
  button in the Security tab of this repo
- **Email** — contact the maintainer directly at [scottbly1@gmail.com](mailto:scottbly1@gmail.com) if you cannot use GitHub's reporting flow

### What to Include

A useful report includes:

- Description of the vulnerability and its potential impact
- Steps to reproduce (minimal reproduction case preferred)
- Which component is affected (`schemas.py`, eval runner, CI pipeline, etc.)
- Whether you believe it affects the eval correctness, data handling, or
  the tool's own security posture

### What to Expect

- **Acknowledgment** within 5 business days
- **Assessment** (confirmed, not confirmed, or needs more info) within 10 business days
- **Fix timeline** communicated once the issue is confirmed
- **Credit** in the changelog if you want it

---

## Scope

In scope for vulnerability reports:

- Eval result integrity — anything that could cause Hermia to falsely pass or fail a model
- Credential or data leakage from the tool itself (not from models under test)
- Supply chain issues in Hermia's own dependencies
- CI/CD pipeline security

Out of scope:

- Vulnerabilities *in the models under test* — that's what Hermia is designed to surface,
  not something we can fix
- Issues requiring physical access to the machine running Hermia
- Social engineering attacks on the maintainer

---

## A Note on the Nature of This Tool

Hermia runs adversarial prompts against language models by design. If you're reviewing
the eval test datasets (`test-datasets/agentic-tasks.json`) and see what look like
prompt injection attempts or instructions to exfiltrate credentials — that's intentional.
Those are the test cases. The tool is supposed to send them to models; it is not supposed
to act on them itself.

If you believe Hermia is *itself* vulnerable to the attack patterns it tests for, that
would be a serious and welcome bug report.
