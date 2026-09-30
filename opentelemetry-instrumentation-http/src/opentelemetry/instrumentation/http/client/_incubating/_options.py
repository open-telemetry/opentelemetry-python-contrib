# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, fields
from typing import Any, Literal

from opentelemetry.instrumentation.http._internal._env import parse_bool_env_var
from opentelemetry.instrumentation.http.client._incubating.environment_variables import (
    OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES,
    OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS,
    OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY,
)

_ATTRIBUTE_FIELDS = (
    "capture_request_body_size",
    "capture_response_body_size",
    "capture_request_size",
    "capture_response_size",
    "capture_url_template",
)
_METRIC_FIELDS = (
    "enable_request_body_size_metric",
    "enable_response_body_size_metric",
    "enable_open_connections_metric",
    "enable_connection_duration_metric",
    "enable_active_requests_metric",
    "capture_network_peer_address",
)


@dataclass(frozen=True, kw_only=True, slots=True)
class HttpClientTelemetryDevelopmentOptions:
    """Development options for :class:`~opentelemetry.instrumentation.http.client.HttpClientTelemetry`.

    .. warning::
        These options are at the **Development** stability level and do NOT
        follow semantic versioning. They may have BREAKING changes in any
        release, including minor and patch releases.

    Every option defaults to ``None``, meaning unset. Unset boolean options
    mean ``False``, so only stable telemetry is emitted unless development
    telemetry is explicitly enabled. Collection options are read once, when the
    telemetry is created.

    Body content may contain sensitive information, so its options can only
    be set in code. It is only recorded when the ``Content-Type`` header marks
    it as textual, decoded with the ``charset`` it declares (UTF-8 by
    default). Binary content is not recorded, because span attributes cannot
    hold byte arrays.

    Attributes:
        capture_request_body_size: Record ``http.request.body.size`` on spans.
        capture_response_body_size: Record ``http.response.body.size`` on
            spans.
        capture_request_size: Record ``http.request.size`` on spans.
        capture_response_size: Record ``http.response.size`` on spans.
        capture_url_template: Record ``url.template`` on spans and on all
            enabled HTTP client metrics, and use it as the span name target.
        user_agent_synthetic_type_detector: Classifies the request's user
            agent string as ``"bot"`` or ``"test"`` traffic, or returns
            ``None`` for genuine traffic. When set, the result is recorded as
            ``user_agent.synthetic.type`` on spans. ``None`` disables the
            attribute.
        capture_request_body_content: Record ``http.request.body.content`` on
            spans, from the chunks passed to
            :meth:`~opentelemetry.instrumentation.http.client.HttpClientOperation.add_request_body`.
        capture_response_body_content: Record ``http.response.body.content``
            on spans, from the chunks passed to
            :meth:`~opentelemetry.instrumentation.http.client.HttpClientOperation.add_response_body`.
        body_content_max_size: Maximum size in bytes of captured body
            content; longer content is truncated on a character boundary.
            ``0`` or less means unbounded, as does leaving it unset, so
            setting a limit is strongly recommended when capturing body
            content.
        enable_request_body_size_metric: Record the
            ``http.client.request.body.size`` metric.
        enable_response_body_size_metric: Record the
            ``http.client.response.body.size`` metric.
        enable_open_connections_metric: Record the
            ``http.client.open_connections`` metric.
        enable_connection_duration_metric: Record the
            ``http.client.connection.duration`` metric.
        enable_active_requests_metric: Record the
            ``http.client.active_requests`` metric.
        capture_network_peer_address: Record ``network.peer.address`` on the
            ``http.client.open_connections`` and
            ``http.client.connection.duration`` metrics.
        sensitive_query_parameters: Case-sensitive query parameter keys whose
            values are recorded as ``REDACTED`` in ``url.full``, fully
            replacing the default list. Unset uses the default list.
        ignore_cancellation_errors: Do not mark requests cancelled by the
            caller as errors: the span status is left unset and
            ``error.type`` is not recorded.
    """

    capture_request_body_size: bool | None = None
    capture_response_body_size: bool | None = None
    capture_request_size: bool | None = None
    capture_response_size: bool | None = None
    capture_url_template: bool | None = None
    user_agent_synthetic_type_detector: Callable[[str], Literal["bot", "test"] | None] | None = None
    capture_request_body_content: bool | None = None
    capture_response_body_content: bool | None = None
    body_content_max_size: int | None = None
    enable_request_body_size_metric: bool | None = None
    enable_response_body_size_metric: bool | None = None
    enable_open_connections_metric: bool | None = None
    enable_connection_duration_metric: bool | None = None
    enable_active_requests_metric: bool | None = None
    capture_network_peer_address: bool | None = None
    sensitive_query_parameters: Collection[str] | None = None
    ignore_cancellation_errors: bool | None = None

    @classmethod
    def from_env(cls) -> HttpClientTelemetryDevelopmentOptions:
        """Create options from environment variables.

        See :mod:`opentelemetry.instrumentation.http.client._incubating.environment_variables`.
        ``OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES`` sets the
        span attribute options, ``OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS``
        sets the metric options (including ``capture_network_peer_address``), and
        ``OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY`` sets both
        unless the more specific variable is set. Unset, empty or invalid
        variables leave their options unset. All other options can only be set
        in code.
        """
        telemetry = parse_bool_env_var(OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY)
        attributes = parse_bool_env_var(OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES)
        metrics = parse_bool_env_var(OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS)
        return cls(
            **dict.fromkeys(_ATTRIBUTE_FIELDS, attributes if attributes is not None else telemetry),
            **dict.fromkeys(_METRIC_FIELDS, metrics if metrics is not None else telemetry),
        )

    def merge(self, other: HttpClientTelemetryDevelopmentOptions) -> HttpClientTelemetryDevelopmentOptions:
        """Return new options where every option set in ``other`` overrides this one."""
        values: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(other, field.name)
            values[field.name] = value if value is not None else getattr(self, field.name)
        return HttpClientTelemetryDevelopmentOptions(**values)
