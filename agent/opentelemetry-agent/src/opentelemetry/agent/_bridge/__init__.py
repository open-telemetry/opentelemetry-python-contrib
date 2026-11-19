# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Bridge from the application's ``opentelemetry-api`` to the agent's vendored API and SDK.

The application's API is a separate copy, with its own globals and types. The vendored sitecustomize
selects the bridge through ``OTEL_PYTHON_CONTEXT`` and ``OTEL_PYTHON_TRACER_PROVIDER``. The application's
API then loads it from this distribution's entry points:

* `context.BridgeRuntimeContext` stores the application's context in the vendored runtime context,
  translating the keys of the current span, baggage and instrumentation suppression, so spans of the
  application and of the vendored instrumentations parent each other.
* `trace.BridgeTracerProvider` creates spans with the vendored tracer provider, wrapped as the
  application's span type.

Only the application's API modules imported by then are imported here: the bridge must not import the
application's ``opentelemetry.trace`` (or any module that does) while its ``opentelemetry.context`` is
still being imported.
"""

from __future__ import annotations

from os import environ

from opentelemetry.agent._vendor.opentelemetry.environment_variables import _AGENT_BRIDGE


def release_environment_variable(name: str) -> None:
    """Unset ``name`` once the application's API has loaded the bridge it selects.

    Child processes inherit the environment. Ones that don't run the agent (another virtual environment,
    or ``PYTHONPATH`` removed) would fail to load the bridge: ``get_tracer_provider()`` raises. Ones
    that run the agent set it again in sitecustomize.
    """
    if environ.get(name) == _AGENT_BRIDGE:
        del environ[name]
