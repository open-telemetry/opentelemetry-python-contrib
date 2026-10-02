# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Sends the shared requests workload with the requests instrumentation on.

``otel-conformance-python`` installs the SDK and nothing else, so this is where
the one instrumentation under test is turned on: explicitly, the way an
application using library instrumentation does. The instrumentation imported
here is this repository's own working-tree
``opentelemetry-instrumentation-requests`` (installed editable by the test env
that runs this scenario), so the conformance run measures the in-development
instrumentation, not a released pin.

Unlike the Flask server scenario, this is a client: the runner starts the mock
HTTP server (declared under ``server:`` in conformance.yaml) and publishes its
address as ``MOCK_SERVER_URL``; the workload drives ``requests`` at it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from opentelemetry.instrumentation.requests import RequestsInstrumentor

# The shared client workload is a sibling module. Import it by path so the
# scenario runs the same whether or not the caller exported a PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import run  # noqa: E402

RequestsInstrumentor().instrument()
run()
