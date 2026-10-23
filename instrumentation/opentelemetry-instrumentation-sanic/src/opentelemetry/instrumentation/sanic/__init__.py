# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
The opentelemetry-instrumentation-sanic package allows tracing HTTP requests
made by the Sanic web framework.

Usage
-----

.. code:: python

    from sanic import Sanic, response
    from opentelemetry.instrumentation.sanic import SanicInstrumentor

    SanicInstrumentor().instrument()

    app = Sanic("myapp")

    @app.get("/")
    async def hello(request):
        return response.text("Hello, world")

The instrumentation is implemented with Sanic request and response middleware
that is registered on every ``Sanic`` application created after the
instrumentor ran. Instrumenting a custom ``Sanic`` subclass is supported: the
middleware is registered by ``Sanic.__init__``, so it is also picked up by
subclasses that call ``super().__init__()``.

Requests are matched against the registered routes by Sanic before request
middleware runs, so the server span is always named after the matched route
template, e.g. ``GET /items/<item_id:int>``.

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from tracking, set the environment variable
``OTEL_PYTHON_SANIC_EXCLUDED_URLS`` (or ``OTEL_PYTHON_EXCLUDED_URLS`` to cover
all instrumentations) to a string of comma delimited regexes that match the
URLs.

For example,

::

    export OTEL_PYTHON_SANIC_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and
``https://site/xyz/healthcheck``.

Capture HTTP request and response headers
*****************************************
You can configure the agent to capture specified HTTP headers as span
attributes, according to the `semantic conventions
<https://github.com/open-telemetry/semantic-conventions/blob/main/docs/http/http-spans.md#http-server-span>`_.

Request headers
***************
To capture HTTP request headers as span attributes, set the environment variable
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`` to a comma
delimited list of HTTP header names.

For example,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="content-type,custom_request_header"

will extract ``content-type`` and ``custom_request_header`` from the request
headers and add them as span attributes.

Regular expressions may also be used to match multiple headers that correspond
to the given pattern. For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="Accept.*,X-.*"

Would match all request headers that start with ``Accept`` and ``X-``.

To capture all request headers, set
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`` to ``".*"``.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST=".*"

The name of the added span attribute will follow the format
``http.request.header.<header_name>`` where ``<header_name>`` is the normalized
HTTP header name (lowercase, with ``-`` replaced by ``_``). The value of the
attribute will be a list containing the header values.

Response headers
****************
To capture HTTP response headers as span attributes, set the environment
variable ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE`` to a
comma delimited list of HTTP header names.

For example,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE="content-type,custom_response_header"

will extract ``content-type`` and ``custom_response_header`` from the response
headers and add them as span attributes.

Sanitizing headers
******************
In order to prevent storing sensitive data such as personally identifiable
information (PII), session keys, passwords, etc, set the environment variable
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS`` to a comma
delimited list of HTTP header names to be sanitized. Regexes may be used, and
all header names will be matched in a case-insensitive manner.

For example,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS=".*session.*,set-cookie"

will replace the value of headers such as ``session-id`` and ``set-cookie``
with ``[REDACTED]`` in the span.

Note:
    The environment variable names used to capture HTTP headers are still
    experimental, and thus are subject to change.

API
---
"""

from __future__ import annotations

from dataclasses import dataclass
from timeit import default_timer

from sanic import Sanic
from wrapt import wrap_function_wrapper

from opentelemetry import context as context_api
from opentelemetry import metrics, trace
from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    _filter_semconv_active_request_count_attr,
    _filter_semconv_duration_attrs,
    _get_schema_url,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _report_old,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
    _set_http_flavor_version,
    _set_http_method,
    _set_http_net_host,
    _set_http_net_host_port,
    _set_http_scheme,
    _set_http_target,
    _set_http_user_agent,
    _set_status,
    _StabilityMode,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.sanic.package import _instruments
from opentelemetry.instrumentation.sanic.version import __version__
from opentelemetry.instrumentation.utils import is_http_instrumentation_enabled, unwrap
from opentelemetry.propagate import extract
from opentelemetry.propagators.textmap import Getter
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_HOST,
    HTTP_ROUTE,
    HTTP_SERVER_NAME,
    HTTP_URL,
)
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.semconv.metrics.http_metrics import (
    HTTP_SERVER_REQUEST_DURATION,
)
from opentelemetry.trace import set_span_in_context
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    SanitizeValue,
    _parse_url_query,
    get_custom_headers,
    get_excluded_urls,
    normalise_request_header_name,
    normalise_response_header_name,
    redact_query_parameters,
    redact_url,
    sanitize_method,
)

tracer = None
meter_old = None
meter_new = None
duration_histogram_old = None
duration_histogram_new = None
active_requests_counter = None
_excluded_urls = None
_sem_conv_opt_in_mode = _StabilityMode.DEFAULT

# Sanic runs request middleware sorted by descending priority and response
# middleware sorted by ascending priority. The instrumentation must be the very
# first request middleware (so that the span is active for user middleware and
# for the route handler) and the very first response middleware (a user
# response middleware that returns a response short-circuits the remaining
# ones, which would otherwise leave the span unclosed).
_REQUEST_MIDDLEWARE_PRIORITY = 2**31 - 1
_RESPONSE_MIDDLEWARE_PRIORITY = -(2**31)

_REQUEST_STATE_ATTR = "_otel_sanic_request_state"


@dataclass
class _RequestState:
    """Per request state shared between the request and response middleware."""

    span: trace.Span
    token: object
    start: float
    request_attrs: dict
    active_requests_count_attrs: dict


def _parse_active_request_count_attrs(
    req_attrs: dict,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> dict:
    return _filter_semconv_active_request_count_attr(
        req_attrs,
        _server_active_requests_count_attrs_old,
        _server_active_requests_count_attrs_new,
        sem_conv_opt_in_mode,
    )


def _parse_duration_attrs(
    req_attrs: dict,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> dict:
    return _filter_semconv_duration_attrs(
        req_attrs,
        _server_duration_attrs_old,
        _server_duration_attrs_new,
        sem_conv_opt_in_mode,
    )


def get_route(request) -> str | None:
    """Returns the matched route template of a request, if any.

    Args:
        request: the request object itself.
    Returns:
        The route template, e.g. ``/items/<item_id:int>``, or ``None`` when no
        route matched the request.
    """
    return getattr(request, "uri_template", None)


def get_default_span_name(request) -> str:
    """Returns the span name.

    Args:
        request: the request object itself.
    Returns:
        The span name as "{method} {route}" of the matched route if possible or
        just "{method}".
    """
    route = get_route(request)
    method = sanitize_method(request.method)
    if method == "_OTHER":
        method = "HTTP"
    if route:
        return f"{method} {route}"
    return f"{method}"


def collect_request_attributes(
    request,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> dict:
    """Collects HTTP request attributes from the Sanic request context
    and returns a dictionary to be used as span creation attributes."""

    result: dict = {}

    _set_http_method(
        result,
        request.method,
        sanitize_method(request.method),
        sem_conv_opt_in_mode,
    )
    _set_http_scheme(
        result,
        request.scheme,
        sem_conv_opt_in_mode,
    )

    server_host = request.server_name
    port = request.server_port
    if server_host:
        _set_http_net_host(result, server_host, sem_conv_opt_in_mode)
        if _report_old(sem_conv_opt_in_mode):
            result[HTTP_HOST] = server_host
    if port:
        _set_http_net_host_port(result, port, sem_conv_opt_in_mode)

    if request.path:
        target = request.path
        if request.query_string:
            target = f"{target}?{request.query_string}"
        redacted_target = redact_query_parameters(target)
        _, redacted_query = _parse_url_query(redacted_target)
        _set_http_target(
            result,
            redacted_target,
            request.path,
            redacted_query,
            sem_conv_opt_in_mode,
        )

    # old semconv v1.20.0 - always set HTTP_URL when reporting old semconv
    if _report_old(sem_conv_opt_in_mode):
        result[HTTP_URL] = redact_url(str(request.url))

    if user_agent := request.headers.get("user-agent"):
        _set_http_user_agent(result, user_agent, sem_conv_opt_in_mode)

    version = getattr(request, "version", None)
    if version:
        _set_http_flavor_version(result, str(version), sem_conv_opt_in_mode)

    route = get_route(request)
    if route:
        result[HTTP_ROUTE] = route

    if _report_old(sem_conv_opt_in_mode):
        server_name = request.host
        if server_name:
            result[HTTP_SERVER_NAME] = server_name

    return result


def collect_request_headers_attributes(request) -> dict[str, list[str]]:
    sanitize = SanitizeValue(get_custom_headers(OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS))

    return sanitize.sanitize_header_values(
        request.headers,
        get_custom_headers(OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST),
        normalise_request_header_name,
    )


def collect_response_headers_attributes(response) -> dict[str, list[str]]:
    sanitize = SanitizeValue(get_custom_headers(OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS))

    return sanitize.sanitize_header_values(
        response.headers,
        get_custom_headers(OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE),
        normalise_response_header_name,
    )


def set_status_code(
    span: trace.Span,
    status_code: int,
    duration_attrs: dict | None = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> None:
    """Adds HTTP response attributes to span using the status_code argument."""
    if duration_attrs is None:
        duration_attrs = {}

    status_code_str = str(status_code)

    try:
        status_code_int = int(status_code)
    except ValueError:
        status_code_int = -1

    _set_status(
        span,
        duration_attrs,
        status_code_int,
        status_code_str,
        server_span=True,
        sem_conv_opt_in_mode=sem_conv_opt_in_mode,
    )


class SanicGetter(Getter):
    """Extract current trace from headers"""

    def get(self, carrier, key: str) -> list | None:
        """Getter implementation to retrieve an HTTP header value from the
        Sanic request context.

        Args:
            carrier: Sanic request context object
            key: header name in request context
        Returns:
            A list of all header values matching the key, or None if the key
            does not match any header.
        """
        headers = carrier.headers
        if not headers:
            return None
        return headers.getall(key, None)

    def keys(self, carrier) -> list:
        return list(carrier.headers.keys())


getter = SanicGetter()


def create_request_middleware(
    tracer_provider: trace.TracerProvider | None = None,
):
    _tracer = (
        tracer_provider.get_tracer(__name__, __version__, schema_url=_get_schema_url(_sem_conv_opt_in_mode))
        if tracer_provider
        else tracer
    )

    async def _request_middleware(request):
        """Sanic request middleware implementing the tracing logic."""
        if not is_http_instrumentation_enabled() or _excluded_urls.url_disabled(request.path):
            return

        route = getattr(request, "route", None)
        if route is not None and getattr(route.extra, "websocket", False):
            # WebSocket routes are not plain HTTP requests and never run the
            # response middleware, so there is no span to close for them.
            return

        span_name = get_default_span_name(request)

        request_attrs = collect_request_attributes(request, _sem_conv_opt_in_mode)
        active_requests_count_attrs = _parse_active_request_count_attrs(
            request_attrs,
            _sem_conv_opt_in_mode,
        )

        parent_context = extract(request, getter=getter)
        span = _tracer.start_span(
            span_name,
            context=parent_context,
            kind=trace.SpanKind.SERVER,
            attributes=request_attrs,
            set_status_on_exception=False,
            record_exception=False,
        )
        if span.is_recording():
            span.set_attributes(collect_request_headers_attributes(request))

        start = default_timer()
        active_requests_counter.add(1, active_requests_count_attrs)

        setattr(
            request.ctx,
            _REQUEST_STATE_ATTR,
            _RequestState(
                span=span,
                token=context_api.attach(set_span_in_context(span, parent_context)),
                start=start,
                request_attrs=request_attrs,
                active_requests_count_attrs=active_requests_count_attrs,
            ),
        )
        return

    return _request_middleware


def create_response_middleware():
    async def _response_middleware(request, response):
        """Sanic response middleware closing the server span."""
        state = getattr(request.ctx, _REQUEST_STATE_ATTR, None)
        if state is None:
            return

        span = state.span
        try:
            set_status_code(
                span,
                response.status,
                state.request_attrs,
                _sem_conv_opt_in_mode,
            )
            if span.is_recording():
                span.set_attributes(collect_response_headers_attributes(response))

            duration_s = default_timer() - state.start
            if duration_histogram_old:
                duration_attrs_old = _parse_duration_attrs(state.request_attrs, _StabilityMode.DEFAULT)
                duration_histogram_old.record(max(round(duration_s * 1000), 0), duration_attrs_old)
            if duration_histogram_new:
                duration_attrs_new = _parse_duration_attrs(state.request_attrs, _StabilityMode.HTTP)
                duration_histogram_new.record(max(duration_s, 0), duration_attrs_new)
            active_requests_counter.add(-1, state.active_requests_count_attrs)
        finally:
            context_api.detach(state.token)
            span.end()
        # Not returning a response keeps the remaining response middleware in
        # the chain running: Sanic stops iterating them as soon as one of them
        # returns a response.
        return

    return _response_middleware


def create_instrumented_app(
    tracer_provider: trace.TracerProvider | None = None,
):
    """Returns a wrapper for ``Sanic.__init__`` registering the tracing
    middleware on every application created after the instrumentor ran.

    Wrapping ``Sanic.__init__`` instead of replacing ``sanic.Sanic`` means the
    instrumentation also applies to code that imported ``Sanic`` before the
    instrumentor ran, and to ``Sanic`` subclasses calling ``super().__init__()``.
    """
    _request_middleware = create_request_middleware(tracer_provider=tracer_provider)
    _response_middleware = create_response_middleware()

    def _wrapped_init(wrapped, instance, args, kwargs):
        wrapped(*args, **kwargs)
        instrument_app(instance, _request_middleware, _response_middleware)

    return _wrapped_init


def instrument_app(app, request_middleware, response_middleware) -> None:
    """Registers the tracing middleware on a Sanic application."""
    app.register_middleware(
        request_middleware,
        attach_to="request",
        priority=_REQUEST_MIDDLEWARE_PRIORITY,
    )
    app.register_middleware(
        response_middleware,
        attach_to="response",
        priority=_RESPONSE_MIDDLEWARE_PRIORITY,
    )


class SanicInstrumentor(BaseInstrumentor):
    # pylint: disable=protected-access
    """An instrumentor for Sanic

    See `BaseInstrumentor`
    """

    def _instrument(self, **kwargs):
        _OpenTelemetrySemanticConventionStability._initialize()
        sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP,
        )

        tracer_provider = kwargs.get("tracer_provider", None)

        global _excluded_urls  # pylint: disable=global-statement
        _excluded_urls = get_excluded_urls("SANIC")

        global _sem_conv_opt_in_mode  # pylint: disable=global-statement
        _sem_conv_opt_in_mode = sem_conv_opt_in_mode

        global tracer  # pylint: disable=global-statement
        tracer = trace.get_tracer(
            __name__,
            __version__,
            schema_url=_get_schema_url(sem_conv_opt_in_mode),
        )

        global meter_old  # pylint: disable=global-statement
        global meter_new  # pylint: disable=global-statement
        global duration_histogram_old  # pylint: disable=global-statement
        global duration_histogram_new  # pylint: disable=global-statement
        global active_requests_counter  # pylint: disable=global-statement

        # Reset the instruments so a re-instrumentation with another semantic
        # convention mode cannot keep recording through the instruments of a
        # previous (possibly shut down) provider.
        meter_old = None
        meter_new = None
        duration_histogram_old = None
        duration_histogram_new = None
        active_requests_counter = None

        if _report_old(sem_conv_opt_in_mode):
            meter_old = metrics.get_meter(
                __name__,
                __version__,
                schema_url=_get_schema_url(_StabilityMode.DEFAULT),
            )
            duration_histogram_old = meter_old.create_histogram(
                name=MetricInstruments.HTTP_SERVER_DURATION,
                unit="ms",
                description="Measures the duration of inbound HTTP requests.",
            )

        if _report_new(sem_conv_opt_in_mode):
            meter_new = metrics.get_meter(
                __name__,
                __version__,
                schema_url=_get_schema_url(_StabilityMode.HTTP),
            )
            duration_histogram_new = meter_new.create_histogram(
                name=HTTP_SERVER_REQUEST_DURATION,
                unit="s",
                description="Duration of HTTP server requests.",
                explicit_bucket_boundaries_advisory=HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
            )

        meter_for_counter = meter_new or meter_old
        active_requests_counter = meter_for_counter.create_up_down_counter(
            name=MetricInstruments.HTTP_SERVER_ACTIVE_REQUESTS,
            unit="{request}",
            description="Number of active HTTP server requests.",
        )

        self._original_sanic_init = Sanic.__init__
        wrap_function_wrapper(
            Sanic,
            "__init__",
            create_instrumented_app(tracer_provider=tracer_provider),
        )

    def _uninstrument(self, **kwargs):
        unwrap(Sanic, "__init__")

    def instrumentation_dependencies(self):
        return _instruments
