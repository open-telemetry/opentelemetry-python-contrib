# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.context import _SUPPRESS_HTTP_INSTRUMENTATION_KEY, set_value
from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.propagators.textmap import Setter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanContext, format_span_id, format_trace_id
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

_URL = "https://example.com"
_TRACEPARENT = "traceparent"


def _traceparent(span_context: SpanContext) -> str:
    return (
        f"00-{format_trace_id(span_context.trace_id)}-{format_span_id(span_context.span_id)}"
        f"-{span_context.trace_flags:02x}"
    )


class _ListSetter(Setter[list[tuple[str, str]]]):
    def set(self, carrier: list[tuple[str, str]], key: str, value: str) -> None:
        carrier.append((key, value))


class TestHttpClientOperationInject(TestBase):
    def _telemetry(
        self,
        options: HttpClientTelemetryOptions | None = None,
        tracer_provider: TracerProvider | None = None,
    ) -> HttpClientTelemetry:
        return HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=tracer_provider or self.tracer_provider,
            propagator=TraceContextTextMapPropagator(),
            options=options,
        )

    def test_injects_span_context(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        carrier: dict[str, str] = {}

        operation.inject(carrier)
        operation.end()

        span_context = operation.span.get_span_context()
        self.assertTrue(span_context.trace_flags.sampled)
        self.assertEqual(carrier, {_TRACEPARENT: _traceparent(span_context)})

    def test_uses_global_propagator_by_default(self) -> None:
        operation = HttpClientTelemetry(instrumenting_module_name="test", tracer_provider=self.tracer_provider).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        carrier: dict[str, str] = {}

        operation.inject(carrier)
        operation.end()

        self.assertIn(_TRACEPARENT, carrier)

    def test_custom_setter(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        carrier: list[tuple[str, str]] = []

        operation.inject(carrier, _ListSetter())
        operation.end()

        self.assertEqual([key for key, _ in carrier], [_TRACEPARENT])

    def test_injects_unsampled_span_context(self) -> None:
        operation = self._telemetry(tracer_provider=TracerProvider(sampler=ALWAYS_OFF)).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        carrier: dict[str, str] = {}

        operation.inject(carrier)
        operation.end()

        self.assertFalse(operation.span.is_recording())
        span_context = operation.span.get_span_context()
        self.assertFalse(span_context.trace_flags.sampled)
        self.assertEqual(carrier, {_TRACEPARENT: _traceparent(span_context)})

    def test_suppressed_injects_nothing(self) -> None:
        operation = self._telemetry().start(
            HttpClientRequest(method="GET", url=_URL), set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
        )
        carrier: dict[str, str] = {}

        operation.inject(carrier)
        operation.end()

        self.assertEqual(carrier, {})

    def test_excluded_url_injects_nothing(self) -> None:
        parent = self.tracer_provider.get_tracer("test").start_span("parent")
        telemetry = self._telemetry(HttpClientTelemetryOptions(excluded_urls=[_URL]))
        operation = telemetry.start(HttpClientRequest(method="GET", url=_URL))
        carrier: dict[str, str] = {}

        operation.inject(carrier)
        operation.end()
        parent.end()

        self.assertEqual(carrier, {})
