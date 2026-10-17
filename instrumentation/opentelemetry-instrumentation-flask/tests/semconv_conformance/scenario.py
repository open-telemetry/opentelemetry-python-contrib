# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Serves the shared Flask app with the Flask instrumentation attached.

``otel-conformance-python`` installs the SDK and nothing else, so this is where
the one instrumentation under test is turned on: explicitly, the way an
application using library instrumentation does. The instrumentation imported
here is this repository's own working-tree
``opentelemetry-instrumentation-flask`` (installed editable by the tox
environment that runs this scenario), so the conformance run measures the
in-development instrumentation, not a released pin.

``otel-http-drive`` runs this from its own process and sends the contract at it
from outside, so nothing loaded here can instrument the sender.
"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from otel_http_test_client import serve

# The shared Flask app is a sibling module. Import it by path so the scenario
# runs the same whether or not the caller exported a PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import create_app  # noqa: E402


def instrumented() -> Flask:
    app = create_app()
    FlaskInstrumentor().instrument_app(app)
    return app


serve(instrumented)
