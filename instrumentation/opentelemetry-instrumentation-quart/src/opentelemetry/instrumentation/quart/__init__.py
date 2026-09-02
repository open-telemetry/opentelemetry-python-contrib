# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Collection
from weakref import WeakSet

import quart

from opentelemetry import trace
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.quart.package import _instruments
from opentelemetry.instrumentation.quart.version import __version__
from opentelemetry.semconv.attributes.http_attributes import HTTP_ROUTE

__all__ = [
    "QuartInstrumentor",
    "__version__",
]


class QuartInstrumentor(BaseInstrumentor):
    _original_quart = None

    @staticmethod
    def instrument_app(app: quart.Quart, tracer_provider=None) -> None:
        if getattr(app, "_is_instrumented_by_opentelemetry", False):
            return

        app._otel_original_asgi_app = app.asgi_app

        app.asgi_app = OpenTelemetryMiddleware(
            app.asgi_app,
            tracer_provider=tracer_provider,
        )

        @app.before_request
        async def _otel_update_route():
            span = trace.get_current_span()

            if span.is_recording() and quart.request.url_rule is not None:
                route = quart.request.url_rule.rule
                method = quart.request.method

                span.set_attribute(
                    HTTP_ROUTE,
                    route,
                )

                span.update_name(f"{method} {route}")

        app._is_instrumented_by_opentelemetry = True
        _InstrumentedQuart._instrumented_quart_apps.add(app)

    @staticmethod
    def uninstrument_app(app: quart.Quart) -> None:
        original_asgi_app = getattr(
            app,
            "_otel_original_asgi_app",
            None,
        )

        if original_asgi_app is not None:
            app.asgi_app = original_asgi_app
            del app._otel_original_asgi_app

        app._is_instrumented_by_opentelemetry = False
        _InstrumentedQuart._instrumented_quart_apps.discard(app)

    def instrumentation_dependencies(  # pylint: disable=no-self-use
        self,
    ) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        self._original_quart = quart.Quart
        _InstrumentedQuart._tracer_provider = kwargs.get("tracer_provider")
        quart.Quart = _InstrumentedQuart

    def _uninstrument(self, **kwargs: Any) -> None:
        for app in list(_InstrumentedQuart._instrumented_quart_apps):
            self.uninstrument_app(app)

        _InstrumentedQuart._instrumented_quart_apps.clear()

        quart.Quart = self._original_quart


class _InstrumentedQuart(quart.Quart):
    _tracer_provider = None
    _instrumented_quart_apps: WeakSet[quart.Quart] = WeakSet()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        QuartInstrumentor.instrument_app(
            self,
            tracer_provider=_InstrumentedQuart._tracer_provider,
        )
