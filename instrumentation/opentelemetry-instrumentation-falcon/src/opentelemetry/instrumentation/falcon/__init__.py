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
* Error from Falcon resources are properly caught and recorded.

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

API
---
"""

from logging import getLogger
from os import environ
from re import compile as re_compile
from re import search
from sys import exc_info

import falcon

import opentelemetry.instrumentation.wsgi as otel_wsgi
from opentelemetry import context, propagators, trace
from opentelemetry.instrumentation.falcon.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    extract_attributes_from_object,
    http_status_to_status_code,
)
from opentelemetry.trace.status import Status
from opentelemetry.util import time_ns

_logger = getLogger(__name__)

_ENVIRON_STARTTIME_KEY = "opentelemetry-falcon.starttime_key"
_ENVIRON_SPAN_KEY = "opentelemetry-falcon.span_key"
_ENVIRON_ACTIVATION_KEY = "opentelemetry-falcon.activation_key"
_ENVIRON_TOKEN = "opentelemetry-falcon.token"
_ENVIRON_EXC = "opentelemetry-falcon.exc"


class _ExcludeList:
    """Class to exclude certain paths (given as a list of regexes) from tracing requests"""

    def __init__(self, excluded_urls):
        self._excluded_urls = excluded_urls
        if self._excluded_urls:
            self._regex = re_compile("|".join(excluded_urls))

    def url_disabled(self, url: str) -> bool:
        return bool(self._excluded_urls and search(self._regex, url))


_root = r"OTEL_PYTHON_{}"


def _get_traced_request_attrs():
    traced_request_attrs = environ.get(
        _root.format("FALCON_TRACED_REQUEST_ATTRS"), []
    )

    if traced_request_attrs:
        traced_request_attrs = [
            traced_request_attr.strip()
            for traced_request_attr in traced_request_attrs.split(",")
        ]

    return traced_request_attrs


def _get_excluded_urls():
    excluded_urls = environ.get(_root.format("FALCON_EXCLUDED_URLS"), [])

    if excluded_urls:
        excluded_urls = [
            excluded_url.strip() for excluded_url in excluded_urls.split(",")
        ]

    return _ExcludeList(excluded_urls)


_excluded_urls = _get_excluded_urls()
_traced_request_attrs = _get_traced_request_attrs()


class FalconInstrumentor(BaseInstrumentor):
    # pylint: disable=protected-access,attribute-defined-outside-init
    """An instrumentor for falcon.API

    See `BaseInstrumentor`
    """

    def _instrument(self, **kwargs):
        self._original_falcon_api = falcon.API
        falcon.API = _InstrumentedFalconAPI

    def _uninstrument(self, **kwargs):
        falcon.API = self._original_falcon_api


class _InstrumentedFalconAPI(falcon.API):
    def __init__(self, *args, **kwargs):
        middlewares = kwargs.pop("middleware", [])
        if not isinstance(middlewares, (list, tuple)):
            middlewares = [middlewares]

        self._tracer = trace.get_tracer(__name__, __version__)
        trace_middleware = _TraceMiddleware(
            self._tracer, kwargs.get("traced_request_attributes")
        )
        middlewares.insert(0, trace_middleware)
        kwargs["middleware"] = middlewares
        super().__init__(*args, **kwargs)

    def __call__(self, env, start_response):
        if _excluded_urls.url_disabled(env.get("PATH_INFO", "/")):
            return super().__call__(env, start_response)

        start_time = time_ns()

        token = context.attach(
            propagators.extract(otel_wsgi.carrier_getter, env)
        )
        span = self._tracer.start_span(
            otel_wsgi.get_default_span_name(env),
            kind=trace.SpanKind.SERVER,
            start_time=start_time,
        )
        if span.is_recording():
            attributes = otel_wsgi.collect_request_attributes(env)
            for key, value in attributes.items():
                span.set_attribute(key, value)

        activation = self._tracer.use_span(span, end_on_exit=True)
        activation.__enter__()
        env[_ENVIRON_SPAN_KEY] = span
        env[_ENVIRON_ACTIVATION_KEY] = activation

        def _start_response(status, response_headers, *args, **kwargs):
            otel_wsgi.add_response_attributes(span, status, response_headers)
            response = start_response(
                status, response_headers, *args, **kwargs
            )
            activation.__exit__(None, None, None)
            context.detach(token)
            return response

        try:
            return super().__call__(env, _start_response)
        except Exception as exc:
            activation.__exit__(
                type(exc), exc, getattr(exc, "__traceback__", None),
            )
            context.detach(token)
            raise


class _TraceMiddleware:
    # pylint:disable=R0201,W0613

    def __init__(self, tracer=None, traced_request_attrs=None):
        self.tracer = tracer
        self._traced_request_attrs = _traced_request_attrs

    def process_request(self, req, resp):
        span = req.env.get(_ENVIRON_SPAN_KEY)
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
        span.update_name(
            "{0}.on_{1}".format(resource_name, req.method.lower())
        )

    def process_response(
        self, req, resp, resource, req_succeeded=None
    ):  # pylint:disable=R0201
        span = req.env.get(_ENVIRON_SPAN_KEY)
        if not span or not span.is_recording():
            return

        status = resp.status
        reason = None
        if resource is None:
            status = "404"
            reason = "NotFound"

        exc_type, exc, _ = exc_info()
        if exc_type and not req_succeeded:
            if "HTTPNotFound" in exc_type.__name__:
                status = "404"
                reason = "NotFound"
            else:
                status = "500"
                reason = "{}: {}".format(exc_type.__name__, exc)

        status = status.split(" ")[0]
        try:
            status_code = int(status)
        except ValueError:
            pass
        finally:
            span.set_attribute("http.status_code", status_code)
            span.set_status(
                Status(
                    status_code=http_status_to_status_code(status_code),
                    description=reason,
                )
            )
