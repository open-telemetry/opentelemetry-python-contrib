# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import dataclasses
import inspect
import re
from unittest import TestCase

from opentelemetry.context import (
    _SUPPRESS_HTTP_INSTRUMENTATION_KEY,
    _SUPPRESS_INSTRUMENTATION_KEY,
    Context,
    attach,
    detach,
    get_current,
    set_value,
)
from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_FULL,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import (
    INVALID_SPAN_CONTEXT,
    SpanKind,
    get_current_span,
    set_span_in_context,
    use_span,
)
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

_BASE_ATTRIBUTES = {HTTP_REQUEST_METHOD: "GET", SERVER_ADDRESS: "example.com", SERVER_PORT: 443}


class TestHttpClientTelemetryInit(TestCase):
    def test_defaults(self) -> None:
        telemetry = HttpClientTelemetry(instrumenting_module_name="test")

        self.assertEqual(telemetry._instrumenting_module_name, "test")
        self.assertEqual(telemetry._schema_url, Schemas.V1_41_1.value)
        self.assertIsNone(telemetry._tracer_provider)
        self.assertIsNone(telemetry._meter_provider)
        self.assertIsNone(telemetry._propagator)
        self.assertEqual(telemetry._options, HttpClientTelemetryOptions())
        self.assertEqual(
            telemetry._development_options,
            HttpClientTelemetryDevelopmentOptions(),
        )

    def test_all_arguments(self) -> None:
        tracer_provider = TracerProvider()
        meter_provider = MeterProvider()
        propagator = TraceContextTextMapPropagator()
        options = HttpClientTelemetryOptions()
        development_options = HttpClientTelemetryDevelopmentOptions()

        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test",
            schema_url=Schemas.V1_40_0.value,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            propagator=propagator,
            options=options,
            development_options=development_options,
        )

        self.assertEqual(telemetry._schema_url, Schemas.V1_40_0.value)
        self.assertIs(telemetry._tracer_provider, tracer_provider)
        self.assertIs(telemetry._meter_provider, meter_provider)
        self.assertIs(telemetry._propagator, propagator)
        self.assertIs(telemetry._options, options)
        self.assertIs(telemetry._development_options, development_options)

    def test_signature(self) -> None:
        parameters = list(inspect.signature(HttpClientTelemetry.__init__).parameters.values())[1:]

        self.assertTrue(all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters))
        self.assertEqual(
            [p.name for p in parameters if p.default is inspect.Parameter.empty],
            ["instrumenting_module_name"],
        )


class TestHttpClientRequest(TestCase):
    def test_user_agent(self) -> None:
        request = HttpClientRequest(method="GET", url="https://example.com", user_agent="Googlebot/2.1")

        self.assertEqual(request.user_agent, "Googlebot/2.1")

    def test_user_agent_default(self) -> None:
        request = HttpClientRequest(method="GET", url="https://example.com")

        self.assertIsNone(request.user_agent)


class TestHttpClientTelemetrySpans(TestBase):
    def _telemetry(
        self,
        options: HttpClientTelemetryOptions | None = None,
        development_options: HttpClientTelemetryDevelopmentOptions | None = None,
    ) -> HttpClientTelemetry:
        return HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            options=options,
            development_options=development_options,
        )

    def _span_name(
        self,
        request: HttpClientRequest,
        options: HttpClientTelemetryOptions | None = None,
        development_options: HttpClientTelemetryDevelopmentOptions | None = None,
    ) -> str:
        self._telemetry(options, development_options).start(request).end()
        (span,) = self.get_finished_spans()
        self.memory_exporter.clear()
        return span.name

    def test_creates_client_span(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com"))

        self.assertTrue(operation.span.is_recording())
        self.assertEqual(self.get_finished_spans(), [])

        operation.end()

        (span,) = self.get_finished_spans()
        self.assertEqual(span.context, operation.span.get_span_context())
        self.assertEqual(span.name, "GET")
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(dict(span.attributes or {}), {**_BASE_ATTRIBUTES, URL_FULL: "https://example.com"})

    def test_instrumentation_scope(self) -> None:
        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test.module",
            instrumenting_library_version="1.2.3",
            schema_url=Schemas.V1_40_0.value,
            tracer_provider=self.tracer_provider,
        )

        telemetry.start(HttpClientRequest(method="GET", url="https://example.com")).end()

        (span,) = self.get_finished_spans()
        self.assertEqual(span.instrumentation_scope.name, "test.module")
        self.assertEqual(span.instrumentation_scope.version, "1.2.3")
        self.assertEqual(span.instrumentation_scope.schema_url, Schemas.V1_40_0.value)

    def test_instrumentation_scope_defaults(self) -> None:
        self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com")).end()

        (span,) = self.get_finished_spans()
        self.assertFalse(span.instrumentation_scope.version)
        self.assertEqual(span.instrumentation_scope.schema_url, Schemas.V1_41_1.value)

    def test_uses_global_tracer_provider_by_default(self) -> None:
        telemetry = HttpClientTelemetry(instrumenting_module_name="test")

        telemetry.start(HttpClientRequest(method="GET", url="https://example.com")).end()

        self.assertEqual(len(self.get_finished_spans()), 1)

    def test_span_name(self) -> None:
        request = HttpClientRequest(method="GET", url="https://example.com")
        templated = HttpClientRequest(method="GET", url="https://example.com/users/1", url_template="/users/{id}")
        capture_url_template = HttpClientTelemetryDevelopmentOptions(capture_url_template=True)
        for case, span_request, options, development_options, expected in (
            *(
                (f"known method {method}", dataclasses.replace(request, method=method), None, None, method)
                for method in ("CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "QUERY", "TRACE")
            ),
            *(
                (f"unknown method {method}", dataclasses.replace(request, method=method), None, None, "HTTP")
                for method in ("FOO", "get", "GeT", "_OTHER")
            ),
            (
                "capture all methods",
                dataclasses.replace(request, method="FOO"),
                HttpClientTelemetryOptions(capture_all_methods=True, known_methods=["GET"]),
                None,
                "FOO",
            ),
            (
                "custom known method",
                dataclasses.replace(request, method="FOO"),
                HttpClientTelemetryOptions(known_methods=["FOO"]),
                None,
                "FOO",
            ),
            (
                "default method not in custom known methods",
                request,
                HttpClientTelemetryOptions(known_methods=["FOO"]),
                None,
                "HTTP",
            ),
            (
                "QUERY not in custom known methods",
                dataclasses.replace(request, method="QUERY"),
                HttpClientTelemetryOptions(known_methods=["GET"]),
                None,
                "HTTP",
            ),
            ("url template", templated, None, capture_url_template, "GET /users/{id}"),
            ("url template is opt-in", templated, None, None, "GET"),
            (
                "url template with unknown method",
                dataclasses.replace(templated, method="FOO"),
                None,
                capture_url_template,
                "HTTP /users/{id}",
            ),
            ("no url template", dataclasses.replace(templated, url_template=None), None, capture_url_template, "GET"),
        ):
            with self.subTest(case):
                self.assertEqual(self._span_name(span_request, options, development_options), expected)

    def test_start_and_end_time(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com"), start_time=100)
        operation.end(end_time=200)

        (span,) = self.get_finished_spans()
        self.assertEqual(span.start_time, 100)
        self.assertEqual(span.end_time, 200)

    def test_end_is_idempotent(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com"))

        operation.end(end_time=200)
        operation.end(end_time=300)

        (span,) = self.get_finished_spans()
        self.assertEqual(span.end_time, 200)

    def test_parent_from_current_context(self) -> None:
        tracer = self.tracer_provider.get_tracer("test")
        with tracer.start_as_current_span("parent") as parent:
            self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com")).end()

        span = self.get_finished_spans().by_name("GET")
        self.assertEqual(span.parent, parent.get_span_context())

    def test_parent_from_explicit_context(self) -> None:
        tracer = self.tracer_provider.get_tracer("test")
        parent = tracer.start_span("parent")
        other = tracer.start_span("other")

        with use_span(other):
            self._telemetry().start(
                HttpClientRequest(method="GET", url="https://example.com"), set_span_in_context(parent)
            ).end()

        (span,) = self.get_finished_spans()
        self.assertEqual(span.parent, parent.get_span_context())

    def test_context_contains_span_without_attaching(self) -> None:
        current = get_current_span()

        operation = self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com"))

        self.assertIs(get_current_span(operation.context), operation.span)
        self.assertIs(get_current_span(), current)
        operation.end()

    def test_instrument_ends_span(self) -> None:
        with self._telemetry().instrument(HttpClientRequest(method="GET", url="https://example.com")) as operation:
            self.assertEqual(self.get_finished_spans(), [])

        (span,) = self.get_finished_spans()
        self.assertEqual(span.context, operation.span.get_span_context())

    def test_instrument_ends_span_and_reraises(self) -> None:
        error = ValueError("boom")

        with self.assertRaises(ValueError) as caught:
            with self._telemetry().instrument(HttpClientRequest(method="GET", url="https://example.com")):
                raise error

        self.assertIs(caught.exception, error)
        self.assertEqual(len(self.get_finished_spans()), 1)


class TestHttpClientTelemetrySkippedSpans(TestBase):
    def _telemetry(self, options: HttpClientTelemetryOptions | None = None) -> HttpClientTelemetry:
        return HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            options=options,
        )

    def _assert_skipped(
        self,
        telemetry: HttpClientTelemetry,
        request: HttpClientRequest,
        context: Context | None = None,
    ) -> None:
        parent = self.tracer_provider.get_tracer("test").start_span("parent")
        parent_context = set_span_in_context(parent, context)

        operation = telemetry.start(request, parent_context)
        operation.end()

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(operation.span.get_span_context(), parent.get_span_context())
        self.assertIs(operation.context, parent_context)
        self.assertEqual(self.get_finished_spans(), [])

    def test_skipped(self) -> None:
        for case, options, url, context in (
            (
                "excluded url string",
                HttpClientTelemetryOptions(excluded_urls=["https://example.com/health"]),
                "https://example.com/health",
                None,
            ),
            (
                "excluded url pattern",
                HttpClientTelemetryOptions(excluded_urls=[re.compile("/health")]),
                "https://example.com/health?full=1",
                None,
            ),
            (
                "instrumentation suppressed in explicit context",
                None,
                "https://example.com",
                set_value(_SUPPRESS_INSTRUMENTATION_KEY, True),
            ),
            (
                "http instrumentation suppressed in explicit context",
                None,
                "https://example.com",
                set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True),
            ),
        ):
            with self.subTest(case):
                self._assert_skipped(self._telemetry(options), HttpClientRequest(method="GET", url=url), context)

    def test_not_excluded_url_is_recorded(self) -> None:
        telemetry = self._telemetry(HttpClientTelemetryOptions(excluded_urls=[re.compile("/health")]))

        telemetry.start(HttpClientRequest(method="GET", url="https://example.com/users")).end()

        self.assertEqual(len(self.get_finished_spans()), 1)

    def test_suppressed_in_current_context(self) -> None:
        for key in (_SUPPRESS_INSTRUMENTATION_KEY, _SUPPRESS_HTTP_INSTRUMENTATION_KEY):
            with self.subTest(key=key):
                token = attach(set_value(key, True))
                try:
                    tracer = self.tracer_provider.get_tracer("test")
                    with tracer.start_as_current_span("parent", end_on_exit=False) as parent:
                        operation = self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com"))
                        operation.end()

                        self.assertFalse(operation.span.is_recording())
                        self.assertEqual(operation.span.get_span_context(), parent.get_span_context())
                        self.assertIs(operation.context, get_current())
                finally:
                    detach(token)

                self.assertEqual(self.get_finished_spans(), [])

    def test_explicit_context_takes_precedence_over_suppressed_current_context(self) -> None:
        token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
        try:
            self._telemetry().start(HttpClientRequest(method="GET", url="https://example.com"), Context()).end()
        finally:
            detach(token)

        self.assertEqual(len(self.get_finished_spans()), 1)

    def test_skipped_without_parent_has_invalid_span_context(self) -> None:
        operation = self._telemetry().start(
            HttpClientRequest(method="GET", url="https://example.com"),
            set_value(_SUPPRESS_INSTRUMENTATION_KEY, True),
        )

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(operation.span.get_span_context(), INVALID_SPAN_CONTEXT)

    def test_skipped_instrument(self) -> None:
        telemetry = self._telemetry(HttpClientTelemetryOptions(excluded_urls=["https://example.com"]))

        with telemetry.instrument(HttpClientRequest(method="GET", url="https://example.com")) as operation:
            self.assertFalse(operation.span.is_recording())

        self.assertEqual(self.get_finished_spans(), [])
