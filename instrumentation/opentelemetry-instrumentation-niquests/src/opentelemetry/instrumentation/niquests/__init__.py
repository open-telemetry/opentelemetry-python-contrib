# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This library allows tracing HTTP requests made by the
`niquests <https://niquests.readthedocs.io/>`_ library.

Niquests is a drop-in replacement for the ``requests`` library with
native async support, HTTP/2, and HTTP/3 capabilities.

Usage
-----

.. code-block:: python

    import niquests
    from opentelemetry.instrumentation.niquests import NiquestsInstrumentor

    # You can optionally pass a custom TracerProvider to instrument().
    NiquestsInstrumentor().instrument()
    response = niquests.get(url="https://www.example.org/")

Async usage:

.. code-block:: python

    import niquests
    from opentelemetry.instrumentation.niquests import NiquestsInstrumentor

    NiquestsInstrumentor().instrument()

    async with niquests.AsyncSession() as session:
        response = await session.get("https://www.example.org/")

Configuration
-------------

Request/Response hooks
**********************

The niquests instrumentation supports extending tracing behavior with the help of
request and response hooks. These are functions that are called back by the instrumentation
right after a Span is created for a request and right before the span is finished processing a response respectively.
The hooks can be configured as follows:

.. code:: python

    import niquests
    from opentelemetry.instrumentation.niquests import NiquestsInstrumentor

    # `request_obj` is an instance of niquests.PreparedRequest
    def request_hook(span, request_obj):
        pass

    # `request_obj` is an instance of niquests.PreparedRequest
    # `response` is an instance of niquests.Response
    def response_hook(span, request_obj, response):
        pass

    NiquestsInstrumentor().instrument(
        request_hook=request_hook, response_hook=response_hook
    )

Capture HTTP request and response headers
*****************************************
You can configure the agent to capture specified HTTP headers as span attributes, according to the
`semantic conventions <https://opentelemetry.io/docs/specs/semconv/http/http-spans/#http-client-span>`_.

Request headers
***************
To capture HTTP request headers as span attributes, set the environment variable
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST`` to a comma delimited list of HTTP header names.

For example using the environment variable,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST="content-type,custom_request_header"

will extract ``content-type`` and ``custom_request_header`` from the request headers and add them as span attributes.

Request header names in Niquests are case-insensitive. So, giving the header name as ``CUStom-Header`` in the environment
variable will capture the header named ``custom-header``.

Regular expressions may also be used to match multiple headers that correspond to the given pattern.  For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST="Accept.*,X-.*"

Would match all request headers that start with ``Accept`` and ``X-``.

To capture all request headers, set ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST`` to ``".*"``.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST=".*"

The name of the added span attribute will follow the format ``http.request.header.<header_name>`` where ``<header_name>``
is the normalized HTTP header name (lowercase, with ``-`` replaced by ``_``). The value of the attribute will be a
single item list containing all the header values.

For example:
``http.request.header.custom_request_header = ["<value1>", "<value2>"]``

Response headers
****************
To capture HTTP response headers as span attributes, set the environment variable
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE`` to a comma delimited list of HTTP header names.

For example using the environment variable,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE="content-type,custom_response_header"

will extract ``content-type`` and ``custom_response_header`` from the response headers and add them as span attributes.

Response header names in Niquests are case-insensitive. So, giving the header name as ``CUStom-Header`` in the environment
variable will capture the header named ``custom-header``.

Regular expressions may also be used to match multiple headers that correspond to the given pattern.  For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE="Content.*,X-.*"

Would match all response headers that start with ``Content`` and ``X-``.

To capture all response headers, set ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE`` to ``".*"``.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE=".*"

The name of the added span attribute will follow the format ``http.response.header.<header_name>`` where ``<header_name>``
is the normalized HTTP header name (lowercase, with ``-`` replaced by ``_``). The value of the attribute will be a
list containing the header values.

For example:
``http.response.header.custom_response_header = ["<value1>", "<value2>"]``

Sanitizing headers
******************
In order to prevent storing sensitive data such as personally identifiable information (PII), session keys, passwords,
etc, set the environment variable ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS``
to a comma delimited list of HTTP header names to be sanitized.

Regexes may be used, and all header names will be matched in a case-insensitive manner.

For example using the environment variable,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS=".*session.*,set-cookie"

will replace the value of headers such as ``session-id`` and ``set-cookie`` with ``[REDACTED]`` in the span.

Note:
    The environment variable names used to capture HTTP headers are still experimental, and thus are subject to change.

Niquests-specific attributes
****************************

This instrumentation leverages niquests' ``conn_info`` metadata to provide
richer telemetry than what is available with plain ``requests``:

Span attributes
    ``tls.protocol.version`` -- TLS version (e.g. ``"1.3"``), from ``conn_info.tls_version``.
    ``tls.cipher`` -- TLS cipher suite, from ``conn_info.cipher``.
    ``revocation_verified`` -- boolean OCSP/CRL verification status, from ``response.ocsp_verified``.

Connection sub-duration histogram metrics (seconds)
    ``http.client.connection.dns.duration`` -- from ``conn_info.resolution_latency``.
    ``http.client.connection.tcp.duration`` -- from ``conn_info.established_latency``.
    ``http.client.connection.tls.duration`` -- from ``conn_info.tls_handshake_latency``.
    ``http.client.request.send.duration`` -- from ``conn_info.request_sent_latency``.

Custom Duration Histogram Boundaries
************************************
To customize the duration histogram bucket boundaries used for HTTP client request duration metrics,
you can provide a list of values when instrumenting:

.. code:: python

    import niquests
    from opentelemetry.instrumentation.niquests import NiquestsInstrumentor

    custom_boundaries = [0.0, 5.0, 10.0, 25.0, 50.0, 100.0]

    NiquestsInstrumentor().instrument(
        duration_histogram_boundaries=custom_boundaries
    )

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_NIQUESTS_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_NIQUESTS_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

API
---
"""

from __future__ import annotations

import functools
import types
from timeit import default_timer
from typing import Any, Callable, Collection, Optional
from urllib.parse import urlparse

from niquests import AsyncSession
from niquests.models import PreparedRequest, Response
from niquests.sessions import Session
from niquests.structures import CaseInsensitiveDict

from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    HTTP_DURATION_HISTOGRAM_BUCKETS_OLD,
    _client_duration_attrs_new,
    _client_duration_attrs_old,
    _filter_semconv_duration_attrs,
    _get_schema_url,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _report_old,
    _set_http_host_client,
    _set_http_method,
    _set_http_net_peer_name_client,
    _set_http_network_protocol_version,
    _set_http_peer_port_client,
    _set_http_scheme,
    _set_http_url,
    _set_status,
    _StabilityMode,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.niquests.package import _instruments
from opentelemetry.instrumentation.niquests.version import __version__
from opentelemetry.instrumentation.utils import (
    is_http_instrumentation_enabled,
    suppress_http_instrumentation,
)
from opentelemetry.metrics import Histogram, get_meter
from opentelemetry.propagate import inject
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_IP,
)
from opentelemetry.semconv._incubating.attributes.tls_attributes import (
    TLS_CIPHER,
    TLS_PROTOCOL_VERSION,
)
from opentelemetry.semconv._incubating.attributes.user_agent_attributes import (
    USER_AGENT_SYNTHETIC_TYPE,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
)
from opentelemetry.semconv.attributes.user_agent_attributes import (
    USER_AGENT_ORIGINAL,
)
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.semconv.metrics.http_metrics import (
    HTTP_CLIENT_REQUEST_DURATION,
)
from opentelemetry.trace import SpanKind, Tracer, get_tracer
from opentelemetry.trace.span import Span
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    ExcludeList,
    detect_synthetic_user_agent,
    get_custom_header_attributes,
    get_custom_headers,
    get_excluded_urls,
    normalise_request_header_name,
    normalise_response_header_name,
    normalize_user_agent,
    parse_excluded_urls,
    redact_url,
    sanitize_method,
)

_excluded_urls_from_env = get_excluded_urls("NIQUESTS")

_RequestHookT = Optional[Callable[[Span, PreparedRequest], None]]
_ResponseHookT = Optional[Callable[[Span, PreparedRequest, Response], None]]


def _set_http_status_code_attribute(
    span,
    status_code,
    metric_attributes=None,
    sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
):
    status_code_str = str(status_code)
    try:
        status_code = int(status_code)
    except ValueError:
        status_code = -1
    if metric_attributes is None:
        metric_attributes = {}
    # When we have durations we should set metrics only once
    # Also the decision to include status code on a histogram should
    # not be dependent on tracing decisions.
    _set_status(
        span,
        metric_attributes,
        status_code,
        status_code_str,
        server_span=False,
        sem_conv_opt_in_mode=sem_conv_opt_in_mode,
    )


def _extract_http_version(result: Response) -> str | None:
    """Extract the HTTP protocol version from a niquests Response.

    Niquests supports HTTP/1.1, HTTP/2, and HTTP/3.
    Returns the version string without the ``HTTP/`` prefix, matching
    the format expected by OpenTelemetry semantic conventions
    (e.g. ``"1.1"``, ``"2"``, ``"3"``).
    """
    raw_version_map = {11: "1.1", 20: "2", 30: "3"}
    try:
        return raw_version_map.get(result.http_version, None)
    except (
        AttributeError
    ):  # Defensive: mocking utilities may omit http_version
        return None


def _extract_tls_version(result: Response) -> str | None:
    """Extract the TLS protocol version from a niquests Response via conn_info.

    Converts from Python's ``ssl.TLSVersion`` enum (e.g. ``TLSv1_3``) to the
    OpenTelemetry semconv format (e.g. ``"1.3"``).

    Returns ``None`` when TLS was not used or the value is unavailable.
    """
    if result.conn_info is None or result.conn_info.tls_version is None:
        return None
    name = result.conn_info.tls_version.name  # e.g. "TLSv1_2", "TLSv1_3"
    if name.startswith("TLSv"):
        return name[4:].replace("_", ".")  # "1_2" -> "1.2"
    return None


def _extract_tls_cipher(result: Response) -> str | None:
    """Extract the TLS cipher suite name from a niquests Response via conn_info.

    Returns ``None`` when TLS was not used or the value is unavailable.
    """
    if result.conn_info is None:
        return None
    return result.conn_info.cipher


def _extract_ip_from_response(result: Response) -> tuple[str, int] | None:
    """Extract destination IP and port from a niquests Response via conn_info.

    Returns (ip, port) tuple or None if not available.
    """
    return result.conn_info.destination_address if result.conn_info else None


def _prepare_span_and_metric_attributes(
    request: PreparedRequest,
    sem_conv_opt_in_mode: _StabilityMode,
    captured_request_headers: list[str] | None,
    sensitive_headers: list[str] | None,
):
    """Build span attributes and metric labels common to both sync and async paths."""
    method = request.method
    span_name = get_default_span_name(method)
    url = redact_url(request.url)

    span_attributes = {}
    _set_http_method(
        span_attributes,
        method,
        sanitize_method(method),
        sem_conv_opt_in_mode,
    )
    _set_http_url(span_attributes, url, sem_conv_opt_in_mode)

    # Check for synthetic user agent type
    headers = (
        request.headers
        if request.headers is not None
        else CaseInsensitiveDict()
    )
    request.headers = headers
    user_agent_value = headers.get("User-Agent")
    user_agent = normalize_user_agent(user_agent_value)
    synthetic_type = detect_synthetic_user_agent(user_agent)
    if synthetic_type:
        span_attributes[USER_AGENT_SYNTHETIC_TYPE] = synthetic_type
    if user_agent:
        span_attributes[USER_AGENT_ORIGINAL] = user_agent
    span_attributes.update(
        get_custom_header_attributes(
            headers,
            captured_request_headers,
            sensitive_headers,
            normalise_request_header_name,
        )
    )

    metric_labels = {}
    _set_http_method(
        metric_labels,
        method,
        sanitize_method(method),
        sem_conv_opt_in_mode,
    )

    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme:
            if _report_old(sem_conv_opt_in_mode):
                _set_http_scheme(
                    metric_labels, parsed_url.scheme, sem_conv_opt_in_mode
                )
        if parsed_url.hostname:
            _set_http_host_client(
                metric_labels, parsed_url.hostname, sem_conv_opt_in_mode
            )
            _set_http_net_peer_name_client(
                metric_labels, parsed_url.hostname, sem_conv_opt_in_mode
            )
            if _report_new(sem_conv_opt_in_mode):
                _set_http_host_client(
                    span_attributes,
                    parsed_url.hostname,
                    sem_conv_opt_in_mode,
                )
                span_attributes[NETWORK_PEER_ADDRESS] = parsed_url.hostname
        if parsed_url.port:
            _set_http_peer_port_client(
                metric_labels, parsed_url.port, sem_conv_opt_in_mode
            )
            if _report_new(sem_conv_opt_in_mode):
                _set_http_peer_port_client(
                    span_attributes, parsed_url.port, sem_conv_opt_in_mode
                )
                span_attributes[NETWORK_PEER_PORT] = parsed_url.port
    except ValueError:
        pass

    return span_name, span_attributes, metric_labels, headers


def _apply_conn_info_attributes(
    span: Span,
    result: Response,
    sem_conv_opt_in_mode: _StabilityMode,
):
    """Set IP, TLS, and revocation span attributes from conn_info."""
    ip_info = _extract_ip_from_response(result)
    if ip_info is not None:
        ip_addr, ip_port = ip_info
        if _report_old(sem_conv_opt_in_mode):
            span.set_attribute(NET_PEER_IP, ip_addr)
        if _report_new(sem_conv_opt_in_mode):
            span.set_attribute(NETWORK_PEER_ADDRESS, ip_addr)
            if ip_port:
                span.set_attribute(NETWORK_PEER_PORT, ip_port)

    tls_version = _extract_tls_version(result)
    if tls_version is not None:
        span.set_attribute(TLS_PROTOCOL_VERSION, tls_version)
    tls_cipher = _extract_tls_cipher(result)
    if tls_cipher is not None:
        span.set_attribute(TLS_CIPHER, tls_cipher)

    if result.ocsp_verified is not None:
        span.set_attribute("tls.revocation.verified", result.ocsp_verified)


def _apply_response_attributes(
    span: Span,
    result: Response,
    metric_labels: dict,
    sem_conv_opt_in_mode: _StabilityMode,
    captured_response_headers: list[str] | None,
    sensitive_headers: list[str] | None,
    response_hook: _ResponseHookT,
    request: PreparedRequest,
):
    """Apply response attributes to span and metric labels."""
    if isinstance(result, Response):
        resp_span_attributes = {}

        if not result.lazy:
            _set_http_status_code_attribute(
                span,
                result.status_code,
                metric_labels,
                sem_conv_opt_in_mode,
            )

        version_text = _extract_http_version(result)

        if version_text:
            _set_http_network_protocol_version(
                metric_labels, version_text, sem_conv_opt_in_mode
            )
            if _report_new(sem_conv_opt_in_mode):
                _set_http_network_protocol_version(
                    resp_span_attributes,
                    version_text,
                    sem_conv_opt_in_mode,
                )

        _apply_conn_info_attributes(span, result, sem_conv_opt_in_mode)

        if not result.lazy:
            resp_span_attributes.update(
                get_custom_header_attributes(
                    result.headers,
                    captured_response_headers,
                    sensitive_headers,
                    normalise_response_header_name,
                )
            )

        for key, val in resp_span_attributes.items():
            span.set_attribute(key, val)

        if callable(response_hook):
            response_hook(span, request, result)


def _record_duration_metrics(
    duration_histogram_old: Histogram | None,
    duration_histogram_new: Histogram | None,
    elapsed_time: float,
    metric_labels: dict,
):
    """Record duration metrics on the appropriate histograms."""
    if duration_histogram_old is not None:
        duration_attrs_old = _filter_semconv_duration_attrs(
            metric_labels,
            _client_duration_attrs_old,
            _client_duration_attrs_new,
            _StabilityMode.DEFAULT,
        )
        duration_histogram_old.record(
            max(round(elapsed_time * 1000), 0),
            attributes=duration_attrs_old,
        )
    if duration_histogram_new is not None:
        duration_attrs_new = _filter_semconv_duration_attrs(
            metric_labels,
            _client_duration_attrs_old,
            _client_duration_attrs_new,
            _StabilityMode.HTTP,
        )
        duration_histogram_new.record(
            elapsed_time, attributes=duration_attrs_new
        )


# Metric names for niquests-specific connection sub-duration histograms.
# These are not part of the OTel HTTP semantic conventions; they are
# custom metrics that leverage niquests' conn_info timing data.
# NOTE: These use the ``http.client.`` prefix for discoverability.  If OTel
# semconv later defines metrics with these exact names, this instrumentation
# must be updated to align with the official definitions.
_CONN_METRIC_DNS_RESOLUTION = "http.client.connection.dns.duration"
_CONN_METRIC_TCP_ESTABLISHMENT = "http.client.connection.tcp.duration"
_CONN_METRIC_TLS_HANDSHAKE = "http.client.connection.tls.duration"
_CONN_METRIC_REQUEST_SEND = "http.client.request.send.duration"

# Maps conn_info attribute names to histogram metric names.
_CONN_INFO_LATENCY_FIELDS = {
    "resolution_latency": _CONN_METRIC_DNS_RESOLUTION,
    "established_latency": _CONN_METRIC_TCP_ESTABLISHMENT,
    "tls_handshake_latency": _CONN_METRIC_TLS_HANDSHAKE,
    "request_sent_latency": _CONN_METRIC_REQUEST_SEND,
}

# Descriptions for each connection sub-duration histogram.
_CONN_HISTOGRAM_DESCRIPTIONS = {
    _CONN_METRIC_DNS_RESOLUTION: "Duration of DNS resolution for HTTP client requests.",
    _CONN_METRIC_TCP_ESTABLISHMENT: "Duration of TCP connection establishment for HTTP client requests.",
    _CONN_METRIC_TLS_HANDSHAKE: "Duration of TLS handshake for HTTP client requests.",
    _CONN_METRIC_REQUEST_SEND: "Duration of sending the HTTP request through the socket.",
}


def _record_connection_metrics(
    connection_histograms: dict[str, Histogram] | None,
    result: Response | None,
    metric_labels: dict,
):
    """Record connection sub-duration metrics from niquests conn_info.

    Each conn_info latency field is a ``datetime.timedelta``; we convert to
    seconds (float) for the histograms.  Fields that are ``None``
    (unavailable) or zero-duration (the phase did not occur, e.g. DNS
    resolution on a reused connection) are silently skipped to avoid
    polluting the histogram with meaningless data points.
    """
    if connection_histograms is None or result is None:
        return
    if not isinstance(result, Response) or result.lazy is not False:
        return
    conn_info = result.conn_info
    if conn_info is None:
        return

    # Use the same metric labels as the main duration histograms.
    # Filter to new-semconv attributes since these are new custom metrics.
    attrs = _filter_semconv_duration_attrs(
        metric_labels,
        _client_duration_attrs_old,
        _client_duration_attrs_new,
        _StabilityMode.HTTP,
    )

    for field, metric_name in _CONN_INFO_LATENCY_FIELDS.items():
        histogram = connection_histograms.get(metric_name)
        if histogram is None:
            continue
        latency = getattr(conn_info, field, None)
        # Skip None (unavailable) and zero-duration (phase did not occur,
        # e.g. DNS resolution on a reused connection).
        if latency is not None and latency.total_seconds() > 0:
            histogram.record(latency.total_seconds(), attributes=attrs)


# pylint: disable=unused-argument
# pylint: disable=R0915
def _instrument(
    tracer: Tracer,
    duration_histogram_old: Histogram,
    duration_histogram_new: Histogram,
    request_hook: _RequestHookT = None,
    response_hook: _ResponseHookT = None,
    excluded_urls: ExcludeList | None = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    captured_request_headers: list[str] | None = None,
    captured_response_headers: list[str] | None = None,
    sensitive_headers: list[str] | None = None,
    connection_histograms: dict[str, Histogram] | None = None,
):
    """Enables tracing of all niquests calls that go through
    :code:`niquests.sessions.Session.send` and
    :code:`niquests.async_session.AsyncSession.send`."""

    wrapped_send = Session.send

    # pylint: disable-msg=too-many-locals,too-many-branches
    @functools.wraps(wrapped_send)
    def instrumented_send(
        self: Session, request: PreparedRequest, **kwargs: Any
    ):
        if excluded_urls and excluded_urls.url_disabled(request.url):
            return wrapped_send(self, request, **kwargs)

        if not is_http_instrumentation_enabled():
            return wrapped_send(self, request, **kwargs)

        span_name, span_attributes, metric_labels, headers = (
            _prepare_span_and_metric_attributes(
                request,
                sem_conv_opt_in_mode,
                captured_request_headers,
                sensitive_headers,
            )
        )

        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            exception = None
            if callable(request_hook):
                request_hook(span, request)

            inject(headers)

            with suppress_http_instrumentation():
                start_time = default_timer()
                try:
                    result = wrapped_send(
                        self, request, **kwargs
                    )  # *** PROCEED
                except Exception as exc:  # pylint: disable=W0703
                    exception = exc
                    result = getattr(exc, "response", None)
                finally:
                    elapsed_time = max(default_timer() - start_time, 0)

            _apply_response_attributes(
                span,
                result,
                metric_labels,
                sem_conv_opt_in_mode,
                captured_response_headers,
                sensitive_headers,
                response_hook,
                request,
            )

            if exception is not None and _report_new(sem_conv_opt_in_mode):
                span.set_attribute(ERROR_TYPE, type(exception).__qualname__)
                metric_labels[ERROR_TYPE] = type(exception).__qualname__

            _record_duration_metrics(
                duration_histogram_old,
                duration_histogram_new,
                elapsed_time,
                metric_labels,
            )

            _record_connection_metrics(
                connection_histograms,
                result,
                metric_labels,
            )

            if exception is not None:
                raise exception.with_traceback(exception.__traceback__)

        return result

    instrumented_send.opentelemetry_instrumentation_niquests_applied = True
    Session.send = instrumented_send

    # Also instrument AsyncSession if available
    _instrument_async(
        tracer,
        duration_histogram_old,
        duration_histogram_new,
        request_hook=request_hook,
        response_hook=response_hook,
        excluded_urls=excluded_urls,
        sem_conv_opt_in_mode=sem_conv_opt_in_mode,
        captured_request_headers=captured_request_headers,
        captured_response_headers=captured_response_headers,
        sensitive_headers=sensitive_headers,
        connection_histograms=connection_histograms,
    )


def _instrument_async(
    tracer: Tracer,
    duration_histogram_old: Histogram,
    duration_histogram_new: Histogram,
    request_hook: _RequestHookT = None,
    response_hook: _ResponseHookT = None,
    excluded_urls: ExcludeList | None = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    captured_request_headers: list[str] | None = None,
    captured_response_headers: list[str] | None = None,
    sensitive_headers: list[str] | None = None,
    connection_histograms: dict[str, Histogram] | None = None,
):
    """Instruments the AsyncSession.send method."""
    wrapped_async_send = AsyncSession.send

    @functools.wraps(wrapped_async_send)
    async def instrumented_async_send(
        self, request: PreparedRequest, **kwargs: Any
    ):
        if excluded_urls and excluded_urls.url_disabled(request.url):
            return await wrapped_async_send(self, request, **kwargs)

        if not is_http_instrumentation_enabled():
            return await wrapped_async_send(self, request, **kwargs)

        span_name, span_attributes, metric_labels, headers = (
            _prepare_span_and_metric_attributes(
                request,
                sem_conv_opt_in_mode,
                captured_request_headers,
                sensitive_headers,
            )
        )

        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            exception = None
            if callable(request_hook):
                request_hook(span, request)

            inject(headers)

            with suppress_http_instrumentation():
                start_time = default_timer()
                try:
                    result = await wrapped_async_send(
                        self, request, **kwargs
                    )  # *** PROCEED
                except Exception as exc:  # pylint: disable=W0703
                    exception = exc
                    result = getattr(exc, "response", None)
                finally:
                    elapsed_time = max(default_timer() - start_time, 0)

            _apply_response_attributes(
                span,
                result,
                metric_labels,
                sem_conv_opt_in_mode,
                captured_response_headers,
                sensitive_headers,
                response_hook,
                request,
            )

            if exception is not None and _report_new(sem_conv_opt_in_mode):
                span.set_attribute(ERROR_TYPE, type(exception).__qualname__)
                metric_labels[ERROR_TYPE] = type(exception).__qualname__

            _record_duration_metrics(
                duration_histogram_old,
                duration_histogram_new,
                elapsed_time,
                metric_labels,
            )

            _record_connection_metrics(
                connection_histograms,
                result,
                metric_labels,
            )

            if exception is not None:
                raise exception.with_traceback(exception.__traceback__)

        return result

    instrumented_async_send.opentelemetry_instrumentation_niquests_applied = (
        True
    )
    AsyncSession.send = instrumented_async_send


def _uninstrument():
    """Disables instrumentation of :code:`niquests` through this module.

    Note that this only works if no other module also patches niquests."""
    _uninstrument_from(Session)
    _uninstrument_from(AsyncSession)


def _uninstrument_from(instr_root, restore_as_bound_func: bool = False):
    instr_func = getattr(instr_root, "send")
    if not getattr(
        instr_func,
        "opentelemetry_instrumentation_niquests_applied",
        False,
    ):
        return

    original = instr_func.__wrapped__  # pylint:disable=no-member
    if restore_as_bound_func:
        original = types.MethodType(original, instr_root)
    setattr(instr_root, "send", original)


def get_default_span_name(method: str) -> str:
    """
    Default implementation for name_callback, returns HTTP {method_name}.
    https://opentelemetry.io/docs/reference/specification/trace/semantic_conventions/http/#name

    Args:
        method: string representing HTTP method
    Returns:
        span name
    """
    method = sanitize_method(method.strip())
    if method == "_OTHER":
        return "HTTP"
    return method


class NiquestsInstrumentor(BaseInstrumentor):
    """An instrumentor for niquests
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """Instruments niquests module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
                ``request_hook``: An optional callback that is invoked right after a span is created.
                ``response_hook``: An optional callback which is invoked right before the span is finished processing a response.
                ``excluded_urls``: A string containing a comma-delimited list of regexes used to exclude URLs from tracking
                ``duration_histogram_boundaries``: A list of float values representing the explicit bucket boundaries for the duration histogram.
        """
        semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP,
        )
        schema_url = _get_schema_url(semconv_opt_in_mode)
        tracer = get_tracer(
            __name__,
            __version__,
            kwargs.get("tracer_provider"),
            schema_url=schema_url,
        )
        excluded_urls = kwargs.get("excluded_urls")
        duration_histogram_boundaries = kwargs.get(
            "duration_histogram_boundaries"
        )
        meter = get_meter(
            __name__,
            __version__,
            kwargs.get("meter_provider"),
            schema_url=schema_url,
        )
        duration_histogram_old = None
        if _report_old(semconv_opt_in_mode):
            duration_histogram_old = meter.create_histogram(
                name=MetricInstruments.HTTP_CLIENT_DURATION,
                unit="ms",
                description="measures the duration of the outbound HTTP request",
                explicit_bucket_boundaries_advisory=duration_histogram_boundaries
                or HTTP_DURATION_HISTOGRAM_BUCKETS_OLD,
            )
        duration_histogram_new = None
        if _report_new(semconv_opt_in_mode):
            duration_histogram_new = meter.create_histogram(
                name=HTTP_CLIENT_REQUEST_DURATION,
                unit="s",
                description="Duration of HTTP client requests.",
                explicit_bucket_boundaries_advisory=duration_histogram_boundaries
                or HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
            )

        # Niquests-specific connection sub-duration histograms.
        # These leverage niquests' conn_info timing data to give
        # visibility into DNS, TCP, TLS, and request-send phases.
        connection_histograms = {
            name: meter.create_histogram(name=name, unit="s", description=desc)
            for name, desc in _CONN_HISTOGRAM_DESCRIPTIONS.items()
        }

        _instrument(
            tracer,
            duration_histogram_old,
            duration_histogram_new,
            request_hook=kwargs.get("request_hook"),
            response_hook=kwargs.get("response_hook"),
            excluded_urls=(
                _excluded_urls_from_env
                if excluded_urls is None
                else parse_excluded_urls(excluded_urls)
            ),
            sem_conv_opt_in_mode=semconv_opt_in_mode,
            captured_request_headers=get_custom_headers(
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST
            ),
            captured_response_headers=get_custom_headers(
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE
            ),
            sensitive_headers=get_custom_headers(
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS
            ),
            connection_histograms=connection_histograms,
        )

    def _uninstrument(self, **kwargs: Any):
        _uninstrument()

    @staticmethod
    def uninstrument_session(session: Session):
        """Disables instrumentation on the session object."""
        _uninstrument_from(session, restore_as_bound_func=True)
