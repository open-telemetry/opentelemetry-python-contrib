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
This library builds on the OpenTelemetry WSGI middleware to track web requests
in Falcon applications. In addition to opentelemetry-instrumentation-wsgi,
it supports falcon-specific features such as:

* The Falcon resource and method name is used as the Span name.
* The ``falcon.resource`` Span attribute is set so the matched resource.
* Errors from Falcon resources are properly caught and recorded.

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from tracking, set the environment variable ``OTEL_PYTHON_FALCON_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` to cover all instrumentations) to a string of comma delimited regexes that match the
URLs.

For example,

::

    export OTEL_PYTHON_FALCON_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

Request attributes
********************
To extract attributes from Falcon's request object and use them as span attributes, set the environment variable
``OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS`` to a comma delimited list of request attribute names.

For example,

::

    export OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS='query_string,uri_template'

will extract the ``query_string`` and ``uri_template`` attributes from every traced request and add them as span attributes.

Falcon Request object reference: https://falcon.readthedocs.io/en/stable/api/request_and_response.html#id1

Usage
-----

.. code-block:: python

    from falcon import API
    from opentelemetry.instrumentation.falcon import FalconInstrumentor

    FalconInstrumentor().instrument()

    app = falcon.API()

    class HelloWorldResource(object):
        def on_get(self, req, resp):
            resp.body = 'Hello World'

    app.add_route('/hello', HelloWorldResource())


Request and Response hooks
***************************
This instrumentation supports request and response hooks. These are functions that get called
right after a span is created for a request and right before the span is finished for the response.
The hooks can be configured as follows:

::

    def request_hook(span, req):
        pass

    def response_hook(span, req, resp):
        pass

    FalconInstrumentation().instrument(request_hook=request_hook, response_hook=response_hook)

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

Request header names in Falcon are case-insensitive and ``-`` characters are replaced by ``_``. So, giving the header
name as ``CUStom_Header`` in the environment variable will capture the header named ``custom-header``.

Regular expressions may also be used to match multiple headers that correspond to the given pattern.  For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="Accept.*,X-.*"

Would match all request headers that start with ``Accept`` and ``X-``.

Additionally, the special keyword ``all`` can be used to capture all request headers.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="all"

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

Response header names in Falcon are case-insensitive. So, giving the header name as ``CUStom-Header`` in the environment
variable will capture the header named ``custom-header``.

Regular expressions may also be used to match multiple headers that correspond to the given pattern.  For example:
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE="Content.*,X-.*"

Would match all response headers that start with ``Content`` and ``X-``.

Additionally, the special keyword ``all`` can be used to capture all response headers.
::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE="all"

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

API
---
"""

from logging import getLogger
from sys import exc_info
from typing import Collection

import falcon
from packaging import version as package_version

import opentelemetry.instrumentation.wsgi as otel_wsgi
from opentelemetry import context, trace
from opentelemetry.instrumentation.falcon.package import _instruments
from opentelemetry.instrumentation.falcon.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.propagators import (
    FuncSetter,
    get_global_response_propagator,
)
from opentelemetry.instrumentation.utils import (
    _start_internal_or_server_span,
    extract_attributes_from_object,
    http_status_to_status_code,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status
from opentelemetry.util._time import _time_ns
from opentelemetry.util.http import get_excluded_urls, get_traced_request_attrs

_logger = getLogger(__name__)

_ENVIRON_STARTTIME_KEY = "opentelemetry-falcon.starttime_key"
_ENVIRON_SPAN_KEY = "opentelemetry-falcon.span_key"
_ENVIRON_ACTIVATION_KEY = "opentelemetry-falcon.activation_key"
_ENVIRON_TOKEN = "opentelemetry-falcon.token"
_ENVIRON_EXC = "opentelemetry-falcon.exc"


_response_propagation_setter = FuncSetter(falcon.Response.append_header)

_parsed_falcon_version = package_version.parse(falcon.__version__)
if _parsed_falcon_version >= package_version.parse("3.0.0"):
    # Falcon 3
    _instrument_app = "App"
    _falcon_version = 3
elif _parsed_falcon_version >= package_version.parse("2.0.0"):
    # Falcon 2
    _instrument_app = "API"
    _falcon_version = 2
else:
    # Falcon 1
    _instrument_app = "API"
    _falcon_version = 1


class _InstrumentedFalconAPI(getattr(falcon, _instrument_app)):
    def __init__(self, *args, **kwargs):
        otel_opts = kwargs.pop("_otel_opts", {})

        # inject trace middleware
        middlewares = kwargs.pop("middleware", [])
        tracer_provider = otel_opts.pop("tracer_provider", None)
        if not isinstance(middlewares, (list, tuple)):
            middlewares = [middlewares]

        self._otel_tracer = trace.get_tracer(
            __name__, __version__, tracer_provider
        )

        trace_middleware = _TraceMiddleware(
            self._otel_tracer,
            otel_opts.pop(
                "traced_request_attributes", get_traced_request_attrs("FALCON")
            ),
            otel_opts.pop("request_hook", None),
            otel_opts.pop("response_hook", None),
        )
        middlewares.insert(0, trace_middleware)
        kwargs["middleware"] = middlewares

        self._otel_excluded_urls = get_excluded_urls("FALCON")
        super().__init__(*args, **kwargs)

    def _handle_exception(
        self, arg1, arg2, arg3, arg4
    ):  # pylint: disable=C0103
        # Falcon 3 does not execute middleware within the context of the exception
        # so we capture the exception here and save it into the env dict

        # Translation layer for handling the changed arg position of "ex" in Falcon > 2 vs
        # Falcon < 2
        if _falcon_version == 1:
            ex = arg1
            req = arg2
            resp = arg3
            params = arg4
        else:
            req = arg1
            resp = arg2
            ex = arg3
            params = arg4

        _, exc, _ = exc_info()
        req.env[_ENVIRON_EXC] = exc

        if _falcon_version == 1:
            return super()._handle_exception(ex, req, resp, params)

        return super()._handle_exception(req, resp, ex, params)

    def __call__(self, env, start_response):
        # pylint: disable=E1101
        if self._otel_excluded_urls.url_disabled(env.get("PATH_INFO", "/")):
            return super().__call__(env, start_response)

        start_time = _time_ns()

        span, token = _start_internal_or_server_span(
            tracer=self._otel_tracer,
            span_name=otel_wsgi.get_default_span_name(env),
            start_time=start_time,
            context_carrier=env,
            context_getter=otel_wsgi.wsgi_getter,
        )

        if span.is_recording():
            attributes = otel_wsgi.collect_request_attributes(env)
            for key, value in attributes.items():
                span.set_attribute(key, value)
            if span.is_recording() and span.kind == trace.SpanKind.SERVER:
                custom_attributes = (
                    otel_wsgi.collect_custom_request_headers_attributes(env)
                )
                if len(custom_attributes) > 0:
                    span.set_attributes(custom_attributes)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()
        env[_ENVIRON_SPAN_KEY] = span
        env[_ENVIRON_ACTIVATION_KEY] = activation

        def _start_response(status, response_headers, *args, **kwargs):
            response = start_response(
                status, response_headers, *args, **kwargs
            )
            activation.__exit__(None, None, None)
            if token is not None:
                context.detach(token)
            return response

        try:
            return super().__call__(env, _start_response)
        except Exception as exc:
            activation.__exit__(
                type(exc),
                exc,
                getattr(exc, "__traceback__", None),
            )
            if token is not None:
                context.detach(token)
            raise


class _TraceMiddleware:
    # pylint:disable=R0201,W0613

    def __init__(
        self,
        tracer=None,
        traced_request_attrs=None,
        request_hook=None,
        response_hook=None,
    ):
        self.tracer = tracer
        self._traced_request_attrs = traced_request_attrs
        self._request_hook = request_hook
        self._response_hook = response_hook

    def process_request(self, req, resp):
        span = req.env.get(_ENVIRON_SPAN_KEY)
        if span and self._request_hook:
            self._request_hook(span, req)

        if not span or not span.is_recording():
            return

        attributes = extract_attributes_from_object(
            req, self._traced_request_attrs
        )
        for key, value in attributes.items():
            span.set_attribute(key, value)

    def process_resource(self, req, resp, resource, params):
        span = req.env.get(_ENVIRON_SPAN_KEY)
        if not span or not span.is_recording():
            return

        resource_name = resource.__class__.__name__
        span.set_attribute("falcon.resource", resource_name)
        span.update_name(f"{resource_name}.on_{req.method.lower()}")

    def process_response(
        self, req, resp, resource, req_succeeded=None
    ):  # pylint:disable=R0201,R0912
        span = req.env.get(_ENVIRON_SPAN_KEY)

        if not span or not span.is_recording():
            return

        status = resp.status
        reason = None
        if resource is None:
            status = "404"
            reason = "NotFound"
        else:
            if _ENVIRON_EXC in req.env:
                exc = req.env[_ENVIRON_EXC]
                exc_type = type(exc)
            else:
                exc_type, exc = None, None
            if exc_type and not req_succeeded:
                if "HTTPNotFound" in exc_type.__name__:
                    status = "404"
                    reason = "NotFound"
                else:
                    status = "500"
                    reason = f"{exc_type.__name__}: {exc}"

        status = status.split(" ")[0]
        try:
            status_code = int(status)
            span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, status_code)
            span.set_status(
                Status(
                    status_code=http_status_to_status_code(
                        status_code, server_span=True
                    ),
                    description=reason,
                )
            )

            # Falcon 1 does not support response headers. So
            # send an empty dict.
            response_headers = {}
            if _falcon_version > 1:
                response_headers = resp.headers

            if span.is_recording() and span.kind == trace.SpanKind.SERVER:
                custom_attributes = (
                    otel_wsgi.collect_custom_response_headers_attributes(
                        response_headers.items()
                    )
                )
                if len(custom_attributes) > 0:
                    span.set_attributes(custom_attributes)
        except ValueError:
            pass

        propagator = get_global_response_propagator()
        if propagator:
            propagator.inject(resp, setter=_response_propagation_setter)

        if self._response_hook:
            self._response_hook(span, req, resp)


class FalconInstrumentor(BaseInstrumentor):
    # pylint: disable=protected-access,attribute-defined-outside-init
    """An instrumentor for falcon.API

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **opts):
        self._original_falcon_api = getattr(falcon, _instrument_app)

        class FalconAPI(_InstrumentedFalconAPI):
            def __init__(self, *args, **kwargs):
                kwargs["_otel_opts"] = opts
                super().__init__(*args, **kwargs)

        setattr(falcon, _instrument_app, FalconAPI)

    def _uninstrument(self, **kwargs):
        setattr(falcon, _instrument_app, self._original_falcon_api)
