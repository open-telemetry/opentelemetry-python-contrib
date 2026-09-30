# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Environment variables read by
:meth:`~opentelemetry.instrumentation.http.client._incubating.HttpClientTelemetryDevelopmentOptions.from_env`.

.. warning::
    These environment variables are at the **Development** stability level and
    do NOT follow semantic versioning. They may have BREAKING changes in any
    release, including minor and patch releases.

Variables accept ``true`` or ``false`` (case-insensitive). Empty values are
treated as unset, and invalid values are ignored with a warning.
"""

OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY = (
    "OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY"
)
"""Emit experimental HTTP client span attributes and metrics.

``OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES`` and
``OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS`` take precedence
when set.
"""

OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES = (
    "OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES"
)
"""Emit experimental HTTP client span attributes.

Records ``http.request.body.size``, ``http.response.body.size``,
``http.request.size`` and ``http.response.size`` on spans, and ``url.template``
on spans and metrics.
"""

OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS = (
    "OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS"
)
"""Emit experimental HTTP client metrics.

Records the ``http.client.request.body.size``,
``http.client.response.body.size``, ``http.client.open_connections``,
``http.client.connection.duration`` and ``http.client.active_requests``
metrics, with ``network.peer.address`` on the connection metrics.
"""
