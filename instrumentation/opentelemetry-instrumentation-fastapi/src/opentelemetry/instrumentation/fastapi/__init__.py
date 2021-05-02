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

import fastapi
from starlette.routing import Match

from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.util.http import get_excluded_urls

_excluded_urls_from_env = get_excluded_urls("FASTAPI")


class FastAPIInstrumentor(BaseInstrumentor):
    """An instrumentor for FastAPI

    See `BaseInstrumentor`
    """

    _original_fastapi = None

    @staticmethod
    def instrument_app(
        app: fastapi.FastAPI,
        tracer_provider=None,
        excluded_urls=None,
    ):
        """Instrument an uninstrumented FastAPI application."""
        if not getattr(app, "is_instrumented_by_opentelemetry", False):
            if excluded_urls is None:
                excluded_urls = _excluded_urls_from_env

            app.add_middleware(
                OpenTelemetryMiddleware,
                excluded_urls=excluded_urls,
                span_details_callback=_get_route_details,
                tracer_provider=tracer_provider,
            )
            app.is_instrumented_by_opentelemetry = True

    def _instrument(self, **kwargs):
        self._original_fastapi = fastapi.FastAPI
        _InstrumentedFastAPI._tracer_provider = kwargs.get("tracer_provider")
        _InstrumentedFastAPI._excluded_urls = kwargs.get("excluded_urls")
        fastapi.FastAPI = _InstrumentedFastAPI

    def _uninstrument(self, **kwargs):
        fastapi.FastAPI = self._original_fastapi


class _InstrumentedFastAPI(fastapi.FastAPI):
    _tracer_provider = None
    _excluded_urls = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        excluded_urls = (
            _InstrumentedFastAPI._excluded_urls
            if _InstrumentedFastAPI._excluded_urls is not None
            else _excluded_urls_from_env
        )
        self.add_middleware(
            OpenTelemetryMiddleware,
            excluded_urls=excluded_urls,
            span_details_callback=_get_route_details,
            tracer_provider=_InstrumentedFastAPI._tracer_provider,
        )


def _get_route_details(scope):
    """Callback to retrieve the fastapi route being served.

    TODO: there is currently no way to retrieve http.route from
    a starlette application from scope.

    See: https://github.com/encode/starlette/pull/804
    """
    app = scope["app"]
    route = None
    for starlette_route in app.routes:
        match, _ = starlette_route.matches(scope)
        if match == Match.FULL:
            route = starlette_route.path
            break
        if match == Match.PARTIAL:
            route = starlette_route.path
    # method only exists for http, if websocket
    # leave it blank.
    span_name = route or scope.get("method", "")
    attributes = {}
    if route:
        attributes[SpanAttributes.HTTP_ROUTE] = route
    return span_name, attributes
