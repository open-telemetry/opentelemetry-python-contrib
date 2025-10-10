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

from logging import getLogger
from time import time_ns
from timeit import default_timer

from pyramid.events import BeforeTraversal
from pyramid.httpexceptions import HTTPException, HTTPServerError
from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW

import opentelemetry.instrumentation.wsgi as otel_wsgi
from opentelemetry import context, trace
from opentelemetry.instrumentation.propagators import (
    get_global_response_propagator,
)
from opentelemetry.instrumentation.pyramid.version import __version__
from opentelemetry.instrumentation.utils import _start_internal_or_server_span
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.http import get_excluded_urls

TWEEN_NAME = "opentelemetry.instrumentation.pyramid.trace_tween_factory"
SETTING_TRACE_ENABLED = "opentelemetry-pyramid.trace_enabled"

_ENVIRON_STARTTIME_KEY = "opentelemetry-pyramid.starttime_key"
_ENVIRON_SPAN_KEY = "opentelemetry-pyramid.span_key"
_ENVIRON_ACTIVATION_KEY = "opentelemetry-pyramid.activation_key"
_ENVIRON_ENABLED_KEY = "opentelemetry-pyramid.tracing_enabled_key"
_ENVIRON_TOKEN = "opentelemetry-pyramid.token"

_logger = getLogger(__name__)


_excluded_urls = get_excluded_urls("PYRAMID")


def includeme(config):
    config.add_settings({SETTING_TRACE_ENABLED: True})

    config.add_subscriber(_before_traversal, BeforeTraversal)
    _insert_tween(config)


def _insert_tween(config):
    settings = config.get_settings()
    tweens = settings.get("pyramid.tweens")
    # If the list is empty, pyramid does not consider the tweens have been
    # set explicitly. And if our tween is already there, nothing to do
    if not tweens or not tweens.strip():
        # Add our tween just before the default exception handler
        config.add_tween(TWEEN_NAME, over=EXCVIEW)


def _before_traversal(event):
    request = event.request
    request_environ = request.environ
    span_name = otel_wsgi.get_default_span_name(request_environ)

    enabled = request_environ.get(_ENVIRON_ENABLED_KEY)
    if enabled is None:
        _logger.warning(
            "OpenTelemetry pyramid tween 'opentelemetry.instrumentation.pyramid.trace_tween_factory'"
            "was not called. Make sure that the tween is included in 'pyramid.tweens' if"
            "the tween list was created manually"
        )
        return

    if not enabled:
        # Tracing not enabled, return
        return

    start_time = request_environ.get(_ENVIRON_STARTTIME_KEY)
    tracer = trace.get_tracer(
        __name__,
        __version__,
        schema_url="https://opentelemetry.io/schemas/1.11.0",
    )

    if request.matched_route:
        span_name = request.matched_route.pattern
    else:
        span_name = otel_wsgi.get_default_span_name(request_environ)

    span, token = _start_internal_or_server_span(
        tracer=tracer,
        span_name=span_name,
        start_time=start_time,
        context_carrier=request_environ,
        context_getter=otel_wsgi.wsgi_getter,
    )

    if span.is_recording():
        attributes = otel_wsgi.collect_request_attributes(request_environ)
        if request.matched_route:
            attributes[SpanAttributes.HTTP_ROUTE] = (
                request.matched_route.pattern
            )
        for key, value in attributes.items():
            span.set_attribute(key, value)
        if span.kind == trace.SpanKind.SERVER:
            custom_attributes = (
                otel_wsgi.collect_custom_request_headers_attributes(
                    request_environ
                )
            )
            if len(custom_attributes) > 0:
                span.set_attributes(custom_attributes)

    activation = trace.use_span(span, end_on_exit=True)
    activation.__enter__()  # pylint: disable=E1101
    request_environ[_ENVIRON_ACTIVATION_KEY] = activation
    request_environ[_ENVIRON_SPAN_KEY] = span
    if token:
        request_environ[_ENVIRON_TOKEN] = token


def trace_tween_factory(handler, registry):
    # pylint: disable=too-many-statements
    settings = registry.settings
    enabled = asbool(settings.get(SETTING_TRACE_ENABLED, True))
    meter = get_meter(
        __name__,
        __version__,
        schema_url="https://opentelemetry.io/schemas/1.11.0",
    )
    duration_histogram = meter.create_histogram(
        name=MetricInstruments.HTTP_SERVER_DURATION,
        unit="ms",
        description="Measures the duration of inbound HTTP requests.",
    )
    active_requests_counter = meter.create_up_down_counter(
        name=MetricInstruments.HTTP_SERVER_ACTIVE_REQUESTS,
        unit="requests",
        description="measures the number of concurrent HTTP requests that are currently in-flight",
    )

    if not enabled:
        # If disabled, make a tween that signals to the
        # BeforeTraversal subscriber that tracing is disabled
        def disabled_tween(request):
            request.environ[_ENVIRON_ENABLED_KEY] = False
            return handler(request)

        return disabled_tween

    # make a request tracing function
    # pylint: disable=too-many-branches
    def trace_tween(request):
        # pylint: disable=E1101, too-many-locals
        if _excluded_urls.url_disabled(request.url):
            request.environ[_ENVIRON_ENABLED_KEY] = False
            # short-circuit when we don't want to trace anything
            return handler(request)

        attributes = otel_wsgi.collect_request_attributes(request.environ)

        request.environ[_ENVIRON_ENABLED_KEY] = True
        request.environ[_ENVIRON_STARTTIME_KEY] = time_ns()
        active_requests_count_attrs = (
            otel_wsgi._parse_active_request_count_attrs(attributes)
        )
        duration_attrs = otel_wsgi._parse_duration_attrs(attributes)

        start = default_timer()
        active_requests_counter.add(1, active_requests_count_attrs)

        response = None
        status = None
        recordable_exc = None

        try:
            response = handler(request)
        except HTTPException as exc:
            # If the exception is a pyramid HTTPException,
            # that's still valuable information that isn't necessarily
            # a 500. For instance, HTTPFound is a 302.
            # As described in docs, Pyramid exceptions are all valid
            # response types
            response = exc
            if isinstance(exc, HTTPServerError):
                recordable_exc = exc
            raise
        except BaseException as exc:
            # In the case that a non-HTTPException is bubbled up we
            # should infer a internal server error and raise
            status = "500 InternalServerError"
            recordable_exc = exc
            raise
        finally:
            duration = max(round((default_timer() - start) * 1000), 0)
            status = getattr(response, "status", status)
            status_code = otel_wsgi._parse_status_code(status)
            if status_code is not None:
                duration_attrs[SpanAttributes.HTTP_STATUS_CODE] = (
                    otel_wsgi._parse_status_code(status)
                )
            duration_histogram.record(duration, duration_attrs)
            active_requests_counter.add(-1, active_requests_count_attrs)
            span = request.environ.get(_ENVIRON_SPAN_KEY)
            enabled = request.environ.get(_ENVIRON_ENABLED_KEY)
            if not span and enabled:
                _logger.warning(
                    "Pyramid environ's OpenTelemetry span missing."
                    "If the OpenTelemetry tween was added manually, make sure"
                    "PyramidInstrumentor().instrument_config(config) is called"
                )
            elif enabled:
                if status is not None:
                    otel_wsgi.add_response_attributes(
                        span,
                        status,
                        getattr(response, "headerlist", None),
                    )

                    if recordable_exc is not None:
                        span.set_status(
                            Status(StatusCode.ERROR, str(recordable_exc))
                        )
                        span.record_exception(recordable_exc)

                if span.is_recording() and span.kind == trace.SpanKind.SERVER:
                    custom_attributes = (
                        otel_wsgi.collect_custom_response_headers_attributes(
                            getattr(response, "headerlist", None)
                        )
                    )
                    if len(custom_attributes) > 0:
                        span.set_attributes(custom_attributes)

                propagator = get_global_response_propagator()
                if propagator and hasattr(response, "headers"):
                    propagator.inject(response.headers)

                activation = request.environ.get(_ENVIRON_ACTIVATION_KEY)

                # Only considering HTTPServerError
                # to make sure 200, 300 and 400 exceptions are not reported as error
                if isinstance(response, HTTPServerError):
                    activation.__exit__(
                        type(response),
                        response,
                        getattr(response, "__traceback__", None),
                    )
                else:
                    activation.__exit__(None, None, None)

                env_token = request.environ.get(_ENVIRON_TOKEN, None)
                if env_token is not None:
                    context.detach(env_token)

        return response

    return trace_tween
