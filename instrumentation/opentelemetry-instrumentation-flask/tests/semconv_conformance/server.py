# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The Flask application the conformance scenario serves.

This is the shared HTTP server workload from the semantic-conventions
conformance repository, kept identical here so this instrumentation is measured
against the same request contract every other language and framework is. See
https://github.com/open-telemetry/semantic-conventions-conformance
(``scenarios/http/python/flask/scenarios/server.py``).

Nothing here turns instrumentation on, and nothing here may: naming one would
defeat the sharing. The routes are declared with Flask's own decorators because
that declaration is what an instrumentation reads ``http.route`` from. Answering
them goes through the contract's ``respond`` rather than a second copy of the
statuses and bodies.
"""

from __future__ import annotations

from flask import Flask, Response, request

from otel_http_test_client import CONTENT_TYPE, respond


def create_app() -> Flask:
    """Build the app, with nothing attached to it.

    A function rather than a module-level app, so the caller decides when it is
    constructed: an instrumentation that wraps an app has to be installed with
    the SDK already in place.
    """
    app = Flask(__name__)

    @app.get("/health")
    def health() -> Response:
        return _answer()

    @app.get("/users/<user_id>")
    def user(user_id: str) -> Response:
        return _answer()

    @app.post("/items")
    def items() -> Response:
        return _answer()

    @app.get("/status/<code>")
    def status(code: str) -> Response:
        return _answer()

    return app


def _answer() -> Response:
    body = request.get_data(as_text=True) or None
    status, payload = respond(request.method, request.path, body)
    return Response(payload, status=status, content_type=CONTENT_TYPE)
