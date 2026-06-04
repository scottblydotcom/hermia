"""SubmissionSink — opt-in, anonymized community submission.

Rows are passed through the default-deny anonymizer before any POST is made.
No identifying data (host, raw text, hardware metrics) can reach the server.

Opt-in design: nothing is sent unless ``--submit`` is explicitly passed on
the CLI.  Dry-run mode prints the payload and exits without any network I/O.

Auth token is read from an environment variable at call time and is never
logged, even at DEBUG level.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from hermia.sink.anonymize import anonymize_row

logger = logging.getLogger(__name__)


class SubmissionSink:
    """Anonymize and POST rows to a community submission endpoint.

    Parameters
    ----------
    endpoint:
        Full URL to POST to.  ``None`` forces dry-run behaviour.
    token_env:
        Name of the environment variable that holds the bearer token.
        The token is read at write-time and never stored or logged.
    dry_run:
        When ``True`` (or when ``endpoint`` is ``None``), print the
        anonymized payload to stdout and make no network request.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        token_env: str = "HERMIA_SUBMIT_TOKEN",  # noqa: S107
        dry_run: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.token_env = token_env
        self.dry_run = dry_run

    def write(self, rows: list[dict[str, Any]]) -> None:
        """Anonymize *rows* and submit (or dry-print) the safe subset."""
        if not rows:
            return

        payload = [anonymize_row(row) for row in rows]

        if self.dry_run or self.endpoint is None:
            print(json.dumps(payload, indent=2))
            return

        # Live submission — read token from env at call time; never log it.
        bearer = os.environ.get(self.token_env, "")
        headers: dict[str, str] = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=5,
            )
            if not response.ok:
                logger.warning(
                    "hermia submit: server returned %s: %s",
                    response.status_code,
                    response.text[:200],
                )
        except requests.exceptions.RequestException as exc:
            logger.warning("hermia submit: request failed (%s)", type(exc).__name__)
