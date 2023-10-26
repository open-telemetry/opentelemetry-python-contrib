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
This library provides a WSGI middleware that can be used on any WSGI framework
(such as Django / Flask / Web.py) to track requests timing through OpenTelemetry.

Usage (Flask)
-------------

.. code-block:: python

    from flask import Flask
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

    app = Flask(__name__)
    app.wsgi_app = OpenTelemetryMiddleware(app.wsgi_app)

    @app.route("/")
    def hello():
        return "Hello!"

    if __name__ == "__main__":
        app.run(debug=True)


Usage (Django)
--------------

Modify the application's ``wsgi.py`` file as shown below.

.. code-block:: python

    import os
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
    from django.core.wsgi import get_wsgi_application

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')

    application = get_wsgi_application()
    application = OpenTelemetryMiddleware(application)

Usage (Web.py)
--------------

.. code-block:: python

    import web
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware
    from cheroot import wsgi

    urls = ('/', 'index')


    class index:

        def GET(self):
            return "Hello, world!"


    if __name__ == "__main__":
        app = web.application(urls, globals())
        func = app.wsgifunc()

        func = OpenTelemetryMiddleware(func)

        server = wsgi.WSGIServer(
            ("localhost", 5100), func, server_name="localhost"
        )
        server.start()

Configuration
-------------

Request/Response hooks
**********************

This instrumentation supports request and response hooks. These are functions that get called
right after a span is created for a request and right before the span is finished for the response.

- The client request hook is called with the internal span and an instance of WSGIEnvironment when the method
  ``receive`` is called.
- The client response hook is called with the internal span, the status of the response and a list of key-value (tuples)
  representing the response headers returned from the response when the method ``send`` is called.

For example,

.. code-block:: python

    def request_hook(span: Span, environ: WSGIEnvironment):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

    def response_hook(span: Span, environ: WSGIEnvironment, status: str, response_headers: List):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

    OpenTelemetryMiddleware(request_hook=request_hook, response_hook=response_hook)

Capture HTTP request and response headers
*****************************************
You can configure the agent to capture specified HTTP headers as span attributes, according to the
`semantic convention <https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/http.md#http-request-and-response-headers>`_.

Request headers
***************
To capture HTTP request headers as span attributes, set the environment variable
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`` to a comma delimited list of HTTP header names.

For example,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="content-type,custom_request_header"

will extract ``content-type`` and ``custom_request_header`` from the request headers and add them as span attributes.

Request header names in WSGI are case-insensitive and ``-`` characters are replaced by ``_``. So, giving the header
name as ``CUStom_Header`` in the environment variable will capture the header named ``custom-header``.

Regular expressions may also be used to match multiple headers that correspond to the given pattern.  For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="Accept.*,X-.*"

Would match all request headers that start with ``Accept`` and ``X-``.

To capture all request headers, set ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST`` to ``".*"``.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST=".*"

The name of the added span attribute will follow the format ``http.request.header.<header_name>`` where ``<header_name>``
is the normalized HTTP header name (lowercase, with ``-`` replaced by ``_``). The value of the attribute will be a
single item list containing all the header values.

For example:
``http.request.header.custom_request_header = ["<value1>,<value2>"]``

Response headers
****************
To capture HTTP response headers as span attributes, set the environment variable
``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE`` to a comma delimited list of HTTP header names.

For example,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE="content-type,custom_response_header"

will extract ``content-type`` and ``custom_response_header`` from the response headers and add them as span attributes.

Response header names in WSGI are case-insensitive. So, giving the header name as ``CUStom-Header`` in the environment
variable will capture the header named ``custom-header``.

Regular expressions may also be used to match multiple headers that correspond to the given pattern.  For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE="Content.*,X-.*"

Would match all response headers that start with ``Content`` and ``X-``.

To capture all response headers, set ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE`` to ``".*"``.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE=".*"

The name of the added span attribute will follow the format ``http.response.header.<header_name>`` where ``<header_name>``
is the normalized HTTP header name (lowercase, with ``-`` replaced by ``_``). The value of the attribute will be a
single item list containing all the header values.

For example:
``http.response.header.custom_response_header = ["<value1>,<value2>"]``

Sanitizing headers
******************
In order to prevent storing sensitive data such as personally identifiable information (PII), session keys, passwords,
etc, set the environment variable ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS``
to a comma delimited list of HTTP header names to be sanitized.  Regexes may be used, and all header names will be
matched in a case-insensitive manner.

For example,
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS=".*session.*,set-cookie"

will replace the value of headers such as ``session-id`` and ``set-cookie`` with ``[REDACTED]`` in the span.

Note:
    The environment variable names used to capture HTTP headers are still experimental, and thus are subject to change.

Sanitizing methods
******************
In order to prevent unbound cardinality for HTTP methods by default nonstandard ones are labeled as ``NONSTANDARD``.
To record all of the names set the environment variable  ``OTEL_PYTHON_INSTRUMENTATION_HTTP_CAPTURE_ALL_METHODS``
to a value that evaluates to true, e.g. ``1``.

API
---
"""

import functools
import typing
from timeit import default_timer
from urllib.parse import urlparse

from opentelemetry import context, trace
from opentelemetry.instrumentation.utils import (
    _start_internal_or_server_span,
    http_status_to_status_code,
    _OpenTelemetryStabilityMode,
    _get_schema_url,
    _report_new,
    _report_old
)
from opentelemetry.instrumentation.wsgi.version import __version__
from opentelemetry.metrics import get_meter
from opentelemetry.propagators.textmap import Getter
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    SanitizeValue,
    get_custom_headers,
    normalise_request_header_name,
    normalise_response_header_name,
    remove_url_credentials,
    sanitize_method,
    parse_http_host,
)

_HTTP_VERSION_PREFIX = "HTTP/"
_CARRIER_KEY_PREFIX = "HTTP_"
_CARRIER_KEY_PREFIX_LEN = len(_CARRIER_KEY_PREFIX)
# TODO: will come through semconv package once updated
_SPAN_ATTRIBUTES_ERROR_TYPE = "error.type"
_METRIC_INSTRUMENTS_HTTP_SERVER_REQUEST_DURATION = "http.server.request.duration"

_duration_attrs_old = [
    SpanAttributes.HTTP_METHOD,
    SpanAttributes.HTTP_HOST,
    SpanAttributes.HTTP_SCHEME,
    SpanAttributes.HTTP_STATUS_CODE,
    SpanAttributes.HTTP_FLAVOR,
    SpanAttributes.HTTP_SERVER_NAME,
    SpanAttributes.NET_HOST_NAME,
    SpanAttributes.NET_HOST_PORT,
]

_duration_attrs_new = [
    _SPAN_ATTRIBUTES_ERROR_TYPE,
    SpanAttributes.HTTP_REQUEST_METHOD,
    SpanAttributes.HTTP_RESPONSE_STATUS_CODE,
    SpanAttributes.HTTP_ROUTE,
    SpanAttributes.NETWORK_PROTOCOL_VERSION,
    SpanAttributes.URL_SCHEME,
]

_active_requests_count_attrs_old = [
    SpanAttributes.HTTP_METHOD,
    SpanAttributes.HTTP_HOST,
    SpanAttributes.HTTP_SCHEME,
    SpanAttributes.HTTP_FLAVOR,
    SpanAttributes.NET_HOST_NAME,
    SpanAttributes.NET_HOST_PORT,
]

_active_requests_count_attrs_new = [
    SpanAttributes.HTTP_REQUEST_METHOD,
    SpanAttributes.URL_SCHEME,
]

class WSGIGetter(Getter[dict]):
    def get(
        self, carrier: dict, key: str
    ) -> typing.Optional[typing.List[str]]:
        """Getter implementation to retrieve a HTTP header value from the
             PEP3333-conforming WSGI environ

        Args:
             carrier: WSGI environ object
             key: header name in environ object
         Returns:
             A list with a single string with the header value if it exists,
             else None.
        """
        environ_key = "HTTP_" + key.upper().replace("-", "_")
        value = carrier.get(environ_key)
        if value is not None:
            return [value]
        return None

    def keys(self, carrier):
        return [
            key[_CARRIER_KEY_PREFIX_LEN:].lower().replace("_", "-")
            for key in carrier
            if key.startswith(_CARRIER_KEY_PREFIX)
        ]


wsgi_getter = WSGIGetter()


def set_string_attribute(dic, key, value):
    if value is not None and not value == "":
        dic[key] = value
        return True
    return False


def set_int_attribute(dic, key, value):
    if value is not None and not value == "":
        dic[key] = int(value)
        return True
    return False


def _parse_target(target, result, sem_conv_opt_in_mode):
    if not target:
        return False

    parts = urlparse(target)

    _set_scheme(result, parts.scheme, sem_conv_opt_in_mode)
    if parts.path and not parts.path == "":
        target = parts.path
        if parts.query and not parts.query == "":
            target += "?" + parts.query
        _set_target(result, target, parts.path, parts.query, sem_conv_opt_in_mode)
        return True

    return False

def _set_scheme(result, scheme, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_SCHEME, scheme)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.URL_SCHEME, scheme)

def _set_target(result, target, path, query, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_TARGET, target)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.URL_PATH, path)
        set_string_attribute(result, SpanAttributes.URL_QUERY, query)

def _parse_scheme_path_and_query(environ, result, sem_conv_opt_in_mode):
    path = environ.get("PATH_INFO")
    if path is None or path == "":
        if _parse_target(environ.get("REQUEST_URI"), result, sem_conv_opt_in_mode) or _parse_target(
            environ.get("RAW_URI"), result, sem_conv_opt_in_mode
        ):
            return

    path = path or "/"
    target = path
    query = environ.get("QUERY_STRING")
    if query and not query == "":
        target += "?" + query
    _set_target(result, target, path, query, sem_conv_opt_in_mode)

def _set_http_method(result, method, sem_conv_opt_in_mode):
    original = method.strip()
    normalized = sanitize_method(original)
    if normalized != original and sem_conv_opt_in_mode != _OpenTelemetryStabilityMode.DEFAULT:
        set_string_attribute(result, SpanAttributes.HTTP_REQUEST_METHOD_ORIGINAL, original)

    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_METHOD, normalized)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_REQUEST_METHOD, normalized)

def _set_host_port(result, host, port, sem_conv_opt_in_mode):
    # TODO: don't set port if default for scheme
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_HOST_NAME, host)
        set_int_attribute(result, SpanAttributes.NET_HOST_PORT, port)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_ADDRESS, host)
        set_int_attribute(result, SpanAttributes.SERVER_PORT, port)

def _set_peer_ip_port(result, environ, sem_conv_opt_in_mode):
    # TODO: support forwarded#for, etc
    x_forwarded_for = environ.get("X-Forwarded-For")
    ip = None
    port = None
    if x_forwarded_for is not None:
        ip = x_forwarded_for
    else:
        ip = environ.get("REMOTE_ADDR")
        port = environ.get("REMOTE_PORT")

    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PEER_IP, ip)
        set_int_attribute(result, SpanAttributes.NET_PEER_PORT, port)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.CLIENT_ADDRESS, ip)
        set_int_attribute(result, SpanAttributes.CLIENT_PORT, port)

def _set_user_agent(result, user_agent, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_USER_AGENT, user_agent)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.USER_AGENT_ORIGINAL, user_agent)


def _set_protocol_version(result, version, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_FLAVOR, version)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NETWORK_PROTOCOL_VERSION, version)

def _parse_http_host(environ):
    # TODO: support forwarded#host, etc
    x_forwarded_host = environ.get("X-Forwarded-Host")
    if x_forwarded_host is not None:
        return parse_http_host(x_forwarded_host)

    (host, port) = parse_http_host(environ.get("HTTP_HOST"))
    return (host or environ.get("SERVER_NAME"), port or environ.get("SERVER_PORT"))

def collect_request_attributes(environ, sem_conv_opt_in_mode):
    """Collects HTTP request attributes from the PEP3333-conforming
    WSGI environ and returns a dictionary to be used as span creation attributes.
    """

    attributes = {}

    _set_http_method(attributes, environ.get("REQUEST_METHOD"), sem_conv_opt_in_mode)
    _set_scheme(attributes, environ.get("wsgi.url_scheme"), sem_conv_opt_in_mode)

    # following https://peps.python.org/pep-3333/#url-reconstruction + falling back to RAW_URI + REQUEST_URI
    (host, port) = _parse_http_host(environ)
    _set_host_port(attributes, host, port, sem_conv_opt_in_mode)
    _parse_scheme_path_and_query(environ, attributes, sem_conv_opt_in_mode)
    _set_user_agent(attributes, environ.get("HTTP_USER_AGENT"), sem_conv_opt_in_mode)
    _set_peer_ip_port(attributes, environ, sem_conv_opt_in_mode)

    http_version = environ.get("SERVER_PROTOCOL", "")
    if http_version.upper().startswith(_HTTP_VERSION_PREFIX):
        http_version = http_version[len(_HTTP_VERSION_PREFIX) :]
    _set_protocol_version(attributes, http_version, sem_conv_opt_in_mode)

    return attributes


def collect_custom_request_headers_attributes(environ):
    """Returns custom HTTP request headers which are configured by the user
    from the PEP3333-conforming WSGI environ to be used as span creation attributes as described
    in the specification https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/http.md#http-request-and-response-headers
    """

    sanitize = SanitizeValue(
        get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS
        )
    )

    headers = {
        key[_CARRIER_KEY_PREFIX_LEN:].replace("_", "-"): val
        for key, val in environ.items()
        if key.startswith(_CARRIER_KEY_PREFIX)
    }

    return sanitize.sanitize_header_values(
        headers,
        get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST
        ),
        normalise_request_header_name,
    )


def collect_custom_response_headers_attributes(response_headers):
    """Returns custom HTTP response headers which are configured by the user from the
    PEP3333-conforming WSGI environ as described in the specification
    https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/http.md#http-request-and-response-headers
    """

    sanitize = SanitizeValue(
        get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS
        )
    )
    response_headers_dict = {}
    if response_headers:
        response_headers_dict = dict(response_headers)

    return sanitize.sanitize_header_values(
        response_headers_dict,
        get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE
        ),
        normalise_response_header_name,
    )


def _parse_status_code(resp_status):
    status_code, _ = resp_status.split(" ", 1)
    try:
        return int(status_code)
    except ValueError:
        return None


def _filter_active_request_count_attrs(req_attrs, sem_conv_opt_in_mode):
    active_requests_count_attrs = {}
    if _report_old(sem_conv_opt_in_mode):
        for attr_key in _active_requests_count_attrs_old:
            if req_attrs.get(attr_key) is not None:
                active_requests_count_attrs[attr_key] = req_attrs[attr_key]
    if _report_new(sem_conv_opt_in_mode):
        for attr_key in _active_requests_count_attrs_new:
            if req_attrs.get(attr_key) is not None:
                active_requests_count_attrs[attr_key] = req_attrs[attr_key]

    return active_requests_count_attrs

def _filter_duration_attrs(req_attrs, sem_conv_opt_in_mode):
    duration_attrs = {}
    # duration is two different metrics depending on sem_conv_opt_in_mode, so no DUP attributes
    allowed_attributes = _duration_attrs_new if sem_conv_opt_in_mode == _OpenTelemetryStabilityMode.HTTP else _duration_attrs_old
    for attr_key in allowed_attributes:
        if req_attrs.get(attr_key) is not None:
            duration_attrs[attr_key] = req_attrs[attr_key]
    return duration_attrs

def _set_status(span, metrics_attributes, status_code_str, status_code, sem_conv_opt_in_mode):
    if (status_code < 0):
        if _report_new(sem_conv_opt_in_mode):
            span.set_attribute(_SPAN_ATTRIBUTES_ERROR_TYPE, status_code_str)
            metrics_attributes[_SPAN_ATTRIBUTES_ERROR_TYPE] = status_code_str

        span.set_status(
            Status(
                StatusCode.ERROR,
                "Non-integer HTTP status: " + status_code_str,
            )
        )

    status = http_status_to_status_code(status_code, server_span=True)

    if _report_old(sem_conv_opt_in_mode):
        span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, status_code)
        metrics_attributes[SpanAttributes.HTTP_STATUS_CODE] = status_code
    if _report_new(sem_conv_opt_in_mode):
        span.set_attribute(SpanAttributes.HTTP_RESPONSE_STATUS_CODE, status_code)
        metrics_attributes[SpanAttributes.HTTP_RESPONSE_STATUS_CODE] = status_code
        if status == StatusCode.ERROR:
            span.set_attribute(_SPAN_ATTRIBUTES_ERROR_TYPE, status_code_str)
            metrics_attributes[_SPAN_ATTRIBUTES_ERROR_TYPE] = status_code_str
    span.set_status(Status(status))

def add_response_attributes(
    span, start_response_status, response_headers, duration_attrs, sem_conv_opt_in_mode
):  # pylint: disable=unused-argument
    """Adds HTTP response attributes to span using the arguments
    passed to a PEP3333-conforming start_response callable.
    """
    if not span.is_recording():
        return
    status_code_str, _ = start_response_status.split(" ", 1)

    status_code = 0
    try:
        status_code = int(status_code_str)
    except ValueError:
        status_code = -1

    _set_status(span, duration_attrs, status_code_str, status_code, sem_conv_opt_in_mode)


def get_default_span_name(environ):
    """
    Default span name is the HTTP method and URL path, or just the method.
    https://github.com/open-telemetry/opentelemetry-specification/pull/3165
    https://opentelemetry.io/docs/reference/specification/trace/semantic_conventions/http/#name

    Args:
        environ: The WSGI environ object.
    Returns:
        The span name.
    """

    method = sanitize_method(environ.get("REQUEST_METHOD", "").strip())
    if method == "_OTHER":
        return "HTTP"
    # There is no routing in WSGI and path should not be in the span name.
    return method


class OpenTelemetryMiddleware:
    """The WSGI application middleware.

    This class is a PEP 3333 conforming WSGI middleware that starts and
    annotates spans for any requests it is invoked with.

    Args:
        wsgi: The WSGI application callable to forward requests to.
        request_hook: Optional callback which is called with the server span and WSGI
                      environ object for every incoming request.
        response_hook: Optional callback which is called with the server span,
                       WSGI environ, status_code and response_headers for every
                       incoming request.
        tracer_provider: Optional tracer provider to use. If omitted the current
                         globally configured one is used.
    """

    def __init__(
        self,
        wsgi,
        request_hook=None,
        response_hook=None,
        tracer_provider=None,
        meter_provider=None,
        sem_conv_opt_in_mode: _OpenTelemetryStabilityMode = _OpenTelemetryStabilityMode.DEFAULT
    ):
        self.wsgi = wsgi
        self.tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=_get_schema_url(sem_conv_opt_in_mode),
        )
        self.meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url=_get_schema_url(sem_conv_opt_in_mode),
        )


        self.duration_histogram_old = None
        if _report_old(sem_conv_opt_in_mode):
            self.duration_histogram_old = self.meter.create_histogram(
                name=MetricInstruments.HTTP_SERVER_DURATION,
                unit="ms",
                description="measures the duration of the inbound HTTP request",
            )
        self.duration_histogram_new = None
        if _report_new(sem_conv_opt_in_mode):
            self.duration_histogram_new = self.meter.create_histogram(
                name=_METRIC_INSTRUMENTS_HTTP_SERVER_REQUEST_DURATION,
                unit="s",
                description="measures the duration of the inbound HTTP request",
            )

        self.active_requests_counter = self.meter.create_up_down_counter(
            name=MetricInstruments.HTTP_SERVER_ACTIVE_REQUESTS,
            unit="{request}",
            description="measures the number of concurrent HTTP requests that are currently in-flight",
        )
        self.request_hook = request_hook
        self.response_hook = response_hook
        self.sem_conv_opt_in_mode = sem_conv_opt_in_mode

    @staticmethod
    def _create_start_response(
        span, start_response, response_hook, duration_attrs, sem_conv_opt_in_mode
    ):
        @functools.wraps(start_response)
        def _start_response(status, response_headers, *args, **kwargs):
            add_response_attributes(span, status, response_headers, duration_attrs, sem_conv_opt_in_mode)

            if span.is_recording() and span.kind == trace.SpanKind.SERVER:
                custom_attributes = collect_custom_response_headers_attributes(
                    response_headers
                )
                if len(custom_attributes) > 0:
                    span.set_attributes(custom_attributes)
            if response_hook:
                response_hook(status, response_headers)
            return start_response(status, response_headers, *args, **kwargs)

        return _start_response

    # pylint: disable=too-many-branches
    def __call__(self, environ, start_response):
        """The WSGI application

        Args:
            environ: A WSGI environment.
            start_response: The WSGI start_response callable.
        """
        attributes = collect_request_attributes(environ, self.sem_conv_opt_in_mode)

        span, token = _start_internal_or_server_span(
            tracer=self.tracer,
            span_name=get_default_span_name(environ),
            start_time=None,
            context_carrier=environ,
            context_getter=wsgi_getter,
            attributes=attributes,
        )
        if span.is_recording() and span.kind == trace.SpanKind.SERVER:
            custom_attributes = collect_custom_request_headers_attributes(
                environ
            )
            if len(custom_attributes) > 0:
                span.set_attributes(custom_attributes)

        if self.request_hook:
            self.request_hook(span, environ)

        response_hook = self.response_hook
        if response_hook:
            response_hook = functools.partial(response_hook, span, environ)

        start = default_timer()

        active_requests_count_attrs = _filter_active_request_count_attrs(
            attributes, self.sem_conv_opt_in_mode
        )
        self.active_requests_counter.add(1, active_requests_count_attrs)
        try:
            with trace.use_span(span):
                start_response = self._create_start_response(
                    span, start_response, response_hook, attributes, self.sem_conv_opt_in_mode
                )
                iterable = self.wsgi(environ, start_response)
                return _end_span_after_iterating(iterable, span, token)
        except Exception as ex:
            if self.sem_conv_opt_in_mode != _OpenTelemetryStabilityMode.DEFAULT:
                if span.is_recording():
                    span.set_attribute(_SPAN_ATTRIBUTES_ERROR_TYPE, type(ex).__qualname__ )
                attributes[_SPAN_ATTRIBUTES_ERROR_TYPE] = type(ex).__qualname__
            span.set_status(Status(StatusCode.ERROR, str(ex)))
            span.end()
            if token is not None:
                context.detach(token)
            raise
        finally:
            duration = default_timer() - start
            if self.duration_histogram_old is not None:
                duration_attrs_old = _filter_duration_attrs(attributes, _OpenTelemetryStabilityMode.DEFAULT)
                self.duration_histogram_old.record(max(round(duration * 1000), 0), duration_attrs_old)
            if self.duration_histogram_new is not None:
                duration_attrs_new = _filter_duration_attrs(attributes, _OpenTelemetryStabilityMode.HTTP)
                self.duration_histogram_new.record(duration, duration_attrs_new)

            self.active_requests_counter.add(-1, active_requests_count_attrs)


# Put this in a subfunction to not delay the call to the wrapped
# WSGI application (instrumentation should change the application
# behavior as little as possible).
def _end_span_after_iterating(iterable, span, token):
    try:
        with trace.use_span(span):
            yield from iterable
    finally:
        close = getattr(iterable, "close", None)
        if close:
            close()
        span.end()
        if token is not None:
            context.detach(token)


# TODO: inherit from opentelemetry.instrumentation.propagators.Setter


class ResponsePropagationSetter:
    def set(self, carrier, key, value):  # pylint: disable=no-self-use
        carrier.append((key, value))


default_response_propagation_setter = ResponsePropagationSetter()
