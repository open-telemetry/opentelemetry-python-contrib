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
`requests <https://requests.readthedocs.io/en/master/>`_ library.

Usage
-----

.. code-block:: python

    import requests
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    # You can optionally pass a custom TracerProvider to instrument().
    RequestsInstrumentor().instrument()
    response = requests.get(url="https://www.example.org/")

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_REQUESTS_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

API
---
"""

import functools
import types
from timeit import default_timer
from typing import Callable, Collection, Optional
from urllib.parse import urlparse

from requests.models import PreparedRequest, Response
from requests.sessions import Session
from requests.structures import CaseInsensitiveDict

from opentelemetry import context

# FIXME: fix the importing of this private attribute when the location of the _SUPPRESS_HTTP_INSTRUMENTATION_KEY is defined.
from opentelemetry.context import _SUPPRESS_HTTP_INSTRUMENTATION_KEY
from opentelemetry.instrumentation._semconv import (
    _filter_duration_attrs,
    _report_old,
    _report_new,
    _set_http_hostname,
    _set_http_method,
    _set_http_net_peer_name,
    _set_http_network_protocol_version,
    _set_http_port,
    _set_http_scheme,
    _set_http_url,
    _set_http_status_code,
    _SPAN_ATTRIBUTES_ERROR_TYPE,
    _SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS,
    _SPAN_ATTRIBUTES_NETWORK_PEER_PORT,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilityMode,
    _OpenTelemetryStabilitySignalType,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.requests.package import _instruments
from opentelemetry.instrumentation.requests.version import __version__
from opentelemetry.instrumentation.utils import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    http_status_to_status_code,
)
from opentelemetry.metrics import Histogram, get_meter
from opentelemetry.propagate import inject
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer, get_tracer
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import Status
from opentelemetry.util.http import (
    ExcludeList,
    get_excluded_urls,
    parse_excluded_urls,
    remove_url_credentials,
    sanitize_method,
)
from opentelemetry.util.http.httplib import set_ip_on_next_http_connection

_excluded_urls_from_env = get_excluded_urls("REQUESTS")

_RequestHookT = Optional[Callable[[Span, PreparedRequest], None]]
_ResponseHookT = Optional[Callable[[Span, PreparedRequest], None]]


# pylint: disable=unused-argument
# pylint: disable=R0915
def _instrument(
    tracer: Tracer,
    duration_histogram_old: Histogram,
    duration_histogram_new: Histogram,
    request_hook: _RequestHookT = None,
    response_hook: _ResponseHookT = None,
    excluded_urls: ExcludeList = None,
    sem_conv_opt_in_mode: _OpenTelemetryStabilityMode = _OpenTelemetryStabilityMode.DEFAULT,
):
    """Enables tracing of all requests calls that go through
    :code:`requests.session.Session.request` (this includes
    :code:`requests.get`, etc.)."""

    # Since
    # https://github.com/psf/requests/commit/d72d1162142d1bf8b1b5711c664fbbd674f349d1
    # (v0.7.0, Oct 23, 2011), get, post, etc are implemented via request which
    # again, is implemented via Session.request (`Session` was named `session`
    # before v1.0.0, Dec 17, 2012, see
    # https://github.com/psf/requests/commit/4e5c4a6ab7bb0195dececdd19bb8505b872fe120)

    wrapped_send = Session.send

    # pylint: disable-msg=too-many-locals,too-many-branches
    @functools.wraps(wrapped_send)
    def instrumented_send(self, request, **kwargs):
        if excluded_urls and excluded_urls.url_disabled(request.url):
            return wrapped_send(self, request, **kwargs)

        def get_or_create_headers():
            request.headers = (
                request.headers
                if request.headers is not None
                else CaseInsensitiveDict()
            )
            return request.headers

        if context.get_value(
            _SUPPRESS_INSTRUMENTATION_KEY
        ) or context.get_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY):
            return wrapped_send(self, request, **kwargs)

        # See
        # https://github.com/open-telemetry/semantic-conventions/blob/main/docs/http/http-spans.md#http-client
        method = request.method
        span_name = get_default_span_name(method)

        url = remove_url_credentials(request.url)

        span_attributes = {}
        _set_http_method(
            span_attributes, method, span_name, sem_conv_opt_in_mode
        )
        _set_http_url(span_attributes, url, sem_conv_opt_in_mode)

        metric_labels = {}
        _set_http_method(
            metric_labels, method, span_name, sem_conv_opt_in_mode
        )

        try:
            parsed_url = urlparse(url)
            if parsed_url.scheme:
                _set_http_scheme(
                    metric_labels, parsed_url.scheme, sem_conv_opt_in_mode
                )
            if parsed_url.hostname:
                _set_http_hostname(
                    metric_labels, parsed_url.hostname, sem_conv_opt_in_mode
                )
                _set_http_net_peer_name(
                    metric_labels, parsed_url.hostname, sem_conv_opt_in_mode
                )
                if _report_new(sem_conv_opt_in_mode):
                    _set_http_hostname(
                        span_attributes,
                        parsed_url.hostname,
                        sem_conv_opt_in_mode,
                    )
                    # Use semconv library when available
                    span_attributes[
                        _SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS
                    ] = parsed_url.hostname
            if parsed_url.port:
                _set_http_port(
                    metric_labels, parsed_url.port, sem_conv_opt_in_mode
                )
                if _report_new(sem_conv_opt_in_mode):
                    _set_http_port(
                        span_attributes, parsed_url.port, sem_conv_opt_in_mode
                    )
                    # Use semconv library when available
                    span_attributes[
                        _SPAN_ATTRIBUTES_NETWORK_PEER_PORT
                    ] = parsed_url.port
        except ValueError:
            pass

        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span, set_ip_on_next_http_connection(span):
            exception = None
            if callable(request_hook):
                request_hook(span, request)

            headers = get_or_create_headers()
            inject(headers)

            token = context.attach(
                context.set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
            )

            start_time = default_timer()

            try:
                result = wrapped_send(self, request, **kwargs)  # *** PROCEED
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                result = getattr(exc, "response", None)
            finally:
                elapsed_time = max(default_timer() - start_time, 0)
                context.detach(token)

            if isinstance(result, Response):
                span_attributes = {}
                if span.is_recording():
                    _set_http_status_code(
                        span_attributes,
                        result.status_code,
                        sem_conv_opt_in_mode,
                    )
                    span.set_status(
                        Status(http_status_to_status_code(result.status_code))
                    )

                _set_http_status_code(
                    metric_labels, result.status_code, sem_conv_opt_in_mode
                )

                if result.raw is not None:
                    version = getattr(result.raw, "version", None)
                    if version:
                        # Only HTTP/1 is supported by requests
                        version_text = "1.1" if version == 11 else "1.0"
                        _set_http_network_protocol_version(
                            metric_labels, version_text, sem_conv_opt_in_mode
                        )
                        if _report_new(sem_conv_opt_in_mode):
                            _set_http_network_protocol_version(
                                span_attributes,
                                version_text,
                                sem_conv_opt_in_mode,
                            )
                for k, v in span_attributes.items():
                    span.set_attribute(k, v)

                if callable(response_hook):
                    response_hook(span, request, result)

            if exception is not None and _report_new(sem_conv_opt_in_mode):
                span.set_attribute(
                    _SPAN_ATTRIBUTES_ERROR_TYPE, type(exception).__name__
                )
                metric_labels[_SPAN_ATTRIBUTES_ERROR_TYPE] = type(
                    exception
                ).__name__

            if duration_histogram_old is not None:
                duration_attrs_old = _filter_duration_attrs(
                    metric_labels, _OpenTelemetryStabilityMode.DEFAULT
                )
                duration_histogram_old.record(
                    max(round(elapsed_time * 1000), 0),
                    attributes=duration_attrs_old,
                )
            if duration_histogram_new is not None:
                duration_attrs_new = _filter_duration_attrs(
                    metric_labels, _OpenTelemetryStabilityMode.HTTP
                )
                duration_histogram_new.record(
                    elapsed_time, attributes=duration_attrs_new
                )

            if exception is not None:
                raise exception.with_traceback(exception.__traceback__)

        return result

    instrumented_send.opentelemetry_instrumentation_requests_applied = True
    Session.send = instrumented_send


def _uninstrument():
    """Disables instrumentation of :code:`requests` through this module.

    Note that this only works if no other module also patches requests."""
    _uninstrument_from(Session)


def _uninstrument_from(instr_root, restore_as_bound_func=False):
    for instr_func_name in ("request", "send"):
        instr_func = getattr(instr_root, instr_func_name)
        if not getattr(
            instr_func,
            "opentelemetry_instrumentation_requests_applied",
            False,
        ):
            continue

        original = instr_func.__wrapped__  # pylint:disable=no-member
        if restore_as_bound_func:
            original = types.MethodType(original, instr_root)
        setattr(instr_root, instr_func_name, original)


def get_default_span_name(method):
    """
    Default implementation for name_callback, returns HTTP {method_name}.
    https://opentelemetry.io/docs/reference/specification/trace/semantic_conventions/http/#name

    Args:
        method: string representing HTTP method
    Returns:
        span name
    """
    return sanitize_method(method.upper().strip())


class RequestsInstrumentor(BaseInstrumentor):
    """An instrumentor for requests
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments requests module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
                ``request_hook``: An optional callback that is invoked right after a span is created.
                ``response_hook``: An optional callback which is invoked right before the span is finished processing a response.
                ``excluded_urls``: A string containing a comma-delimited
                    list of regexes used to exclude URLs from tracking
        """
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        excluded_urls = kwargs.get("excluded_urls")
        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP,
        )
        duration_histogram_old = None
        if _report_old(semconv_opt_in_mode):
            duration_histogram_old = meter.create_histogram(
                name=MetricInstruments.HTTP_CLIENT_DURATION,
                unit="ms",
                description="measures the duration of the outbound HTTP request",
            )
        duration_histogram_new = None
        if _report_new(semconv_opt_in_mode):
            duration_histogram_new = meter.create_histogram(
                name=MetricInstruments.HTTP_CLIENT_DURATION,
                unit="s",
                description="Duration of HTTP client requests.",
            )
        _instrument(
            tracer,
            duration_histogram_old,
            duration_histogram_new,
            request_hook=kwargs.get("request_hook"),
            response_hook=kwargs.get("response_hook"),
            excluded_urls=_excluded_urls_from_env
            if excluded_urls is None
            else parse_excluded_urls(excluded_urls),
            sem_conv_opt_in_mode=semconv_opt_in_mode,
        )

    def _uninstrument(self, **kwargs):
        _uninstrument()

    @staticmethod
    def uninstrument_session(session):
        """Disables instrumentation on the session object."""
        _uninstrument_from(session, restore_as_bound_func=True)
