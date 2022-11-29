from logging import getLogger
from time import time_ns
from timeit import default_timer
from typing import Collection

from opentelemetry.util.http import parse_excluded_urls, get_excluded_urls
import cherrypy
from opentelemetry.instrumentation.cherrypy.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import _start_internal_or_server_span
import opentelemetry.instrumentation.wsgi as otel_wsgi
from opentelemetry.instrumentation.propagators import (
    get_global_response_propagator,
)
from opentelemetry import trace, context
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.instrumentation.cherrypy.version import __version__
from opentelemetry.metrics import get_meter


_logger = getLogger(__name__)
_excluded_urls_from_env = get_excluded_urls("CHERRYPY")


class CherryPyInstrumentor(BaseInstrumentor):
    """An instrumentor for FastAPI

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        self._original_cherrypy_application = cherrypy._cptree.Application
        cherrypy._cptree.Application = _InstrumentedCherryPyApplication
        cherrypy.Application = _InstrumentedCherryPyApplication

    def _uninstrument(self, **kwargs):
        cherrypy.Application = self._original_cherrypy_application


class _InstrumentedCherryPyApplication(cherrypy._cptree.Application):
    def __init__(self, *args, **kwargs):
        tracer_provider = kwargs.pop('tracer_provider', None)
        meter_provider = kwargs.pop('metr_provider', None)
        self._otel_tracer = trace.get_tracer(
            __name__, __version__, tracer_provider
        )
        otel_meter = get_meter(__name__, __version__, meter_provider)
        self.duration_histogram = otel_meter.create_histogram(
            name="http.server.duration",
            unit="ms",
            description="measures the duration of the inbound HTTP request",
        )
        self.active_requests_counter = otel_meter.create_up_down_counter(
            name="http.server.active_requests",
            unit="requests",
            description="measures the number of concurrent HTTP requests that are currently in-flight",
        )
        self.request_hook = kwargs.pop('request_hook', None)
        self.response_hook = kwargs.pop('response_hook', None)
        excluded_urls = kwargs.pop('excluded_urls', None)
        self._otel_excluded_urls = (
            _excluded_urls_from_env
            if excluded_urls is None
            else parse_excluded_urls(excluded_urls)
        )
        self._is_instrumented_by_opentelemetry = True
        super().__init__(*args, **kwargs)

    def __call__(self, environ, start_response):
        if self._otel_excluded_urls.url_disabled(
            environ.get('PATH_INFO', '/')
        ):
            return super().__call__(environ, start_response)

        if not self._is_instrumented_by_opentelemetry:
            return super().__call__(environ, start_response)

        start_time = time_ns()
        span, token = _start_internal_or_server_span(
            tracer=self._otel_tracer,
            span_name=otel_wsgi.get_default_span_name(environ),
            start_time=start_time,
            context_carrier=environ,
            context_getter=otel_wsgi.wsgi_getter,
        )
        if self.request_hook:
            self.request_hook(span, environ)
        attributes = otel_wsgi.collect_request_attributes(environ)
        active_requests_count_attrs = (
            otel_wsgi._parse_active_request_count_attrs(attributes)
        )
        duration_attrs = otel_wsgi._parse_duration_attrs(attributes)
        self.active_requests_counter.add(1, active_requests_count_attrs)

        if span.is_recording():
            for key, value in attributes.items():
                span.set_attribute(key, value)
            if span.is_recording() and span.kind == trace.SpanKind.SERVER:
                custom_attributes = (
                    otel_wsgi.collect_custom_request_headers_attributes(
                        environ
                    )
                )
                if len(custom_attributes) > 0:
                    span.set_attributes(custom_attributes)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()

        def _start_response(status, response_headers, *args, **kwargs):
            propagator = get_global_response_propagator()
            if propagator:
                propagator.inject(
                    response_headers,
                    setter=otel_wsgi.default_response_propagation_setter,
                )
            
            if span:
                otel_wsgi.add_response_attributes(
                    span, status, response_headers
                )
                status_code = otel_wsgi._parse_status_code(status)
                if status_code is not None:
                    duration_attrs[
                        SpanAttributes.HTTP_STATUS_CODE
                    ] = status_code
                if span.is_recording() and span.kind == trace.SpanKind.SERVER:
                    custom_attributes = (
                        otel_wsgi.collect_custom_response_headers_attributes(
                            response_headers
                        )
                    )
                    if len(custom_attributes) > 0:
                        span.set_attributes(custom_attributes)

            if self.response_hook:
                self.response_hook(span, status, response_headers)
            return start_response(status, response_headers, *args, **kwargs)

        exception = None
        start = default_timer()
        try:
            return super().__call__(environ, _start_response)
        except Exception as exc:
            exception = exc
            raise
        finally:
            if exception is None:
                activation.__exit__(None, None, None)
            else:
                activation.__exit__(
                    type(exc),
                    exc,
                    getattr(exc, "__traceback__", None),
                )
            if token is not None:
                context.detach(token)
            duration = max(round((default_timer() - start) * 1000), 0)
            self.duration_histogram.record(duration, duration_attrs)
            self.active_requests_counter.add(-1, active_requests_count_attrs)
