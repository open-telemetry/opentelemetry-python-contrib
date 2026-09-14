# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The requests workload the conformance scenario sends.

This is the shared HTTP client workload from the semantic-conventions
conformance repository, kept identical here so this instrumentation is measured
against the same request contract every other language and framework is. See
https://github.com/open-telemetry/semantic-conventions-conformance
(``scenarios/http/python/requests/scenarios/client.py``).

Nothing here turns instrumentation on, and nothing here may: naming one would
defeat the sharing. Only the send is this library's; the sequence, the answers,
and the checking are the contract's, so a client is measured against exactly
what a server scenario would have answered.
"""

from __future__ import annotations

import os

import requests

from otel_http_test_client import CONTENT_TYPE, USER_AGENT, drive


def run() -> None:
    """Send the contract at the mock server the runner started."""
    base_url = os.environ.get("MOCK_SERVER_URL")
    if not base_url:
        raise RuntimeError(
            "MOCK_SERVER_URL is not set — the runner publishes it for the "
            "server the package declares"
        )

    # One session for the whole sequence, so the requests share a connection
    # the way an application's would.
    with requests.Session() as session:

        def send(method: str, url: str, body: str | None) -> tuple[int, str]:
            headers = {"User-Agent": USER_AGENT}
            if body is not None:
                headers["Content-Type"] = CONTENT_TYPE
            # A 4xx or 5xx is what the contract asked for, so it comes back as a
            # status: requests raises for one only when told to.
            response = session.request(
                method,
                url,
                data=None if body is None else body.encode("utf-8"),
                headers=headers,
            )
            return response.status_code, response.text

        drive(base_url, send)
