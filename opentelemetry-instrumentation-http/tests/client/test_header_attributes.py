# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re

from tests._util import RecordingSampler

from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientResponse,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_FULL,
)
from opentelemetry.test.test_base import TestBase

_BASE_ATTRIBUTES = {HTTP_REQUEST_METHOD: "GET", SERVER_ADDRESS: "example.com", SERVER_PORT: 443}


class TestHttpClientTelemetryHeaders(TestBase):
    def _telemetry(self, options: HttpClientTelemetryOptions | None = None) -> HttpClientTelemetry:
        return HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            options=options,
        )

    def test_no_headers_captured_by_default(self) -> None:
        operation = self._telemetry().start(
            HttpClientRequest(method="GET", url="https://example.com", headers={"Content-Type": "text/plain"})
        )
        operation.set_response(HttpClientResponse(status_code=200, headers={"Content-Type": "text/plain"}))
        operation.end()

        (span,) = self.get_finished_spans()
        self.assertEqual(
            dict(span.attributes or {}),
            {**_BASE_ATTRIBUTES, URL_FULL: "https://example.com", HTTP_RESPONSE_STATUS_CODE: 200},
        )

    def test_request_headers(self) -> None:
        telemetry = self._telemetry(
            HttpClientTelemetryOptions(
                captured_request_headers=["content-type", re.compile("x-custom-.*")],
                sanitized_headers=[re.compile("x-custom-secret")],
            )
        )

        telemetry.start(
            HttpClientRequest(
                method="GET",
                url="https://example.com",
                headers={
                    "Content-Type": "text/plain",
                    "X-Custom-A": ["1", "2"],
                    "X-Custom-Secret": "secret",
                    "Accept": "*/*",
                },
            )
        ).end()

        (span,) = self.get_finished_spans()
        self.assertEqual(
            dict(span.attributes or {}),
            {
                **_BASE_ATTRIBUTES,
                URL_FULL: "https://example.com",
                "http.request.header.content-type": ("text/plain",),
                "http.request.header.x-custom-a": ("1", "2"),
                "http.request.header.x-custom-secret": ("[REDACTED]",),
            },
        )

    def test_request_headers_are_available_to_sampler(self) -> None:
        sampler = RecordingSampler()
        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=TracerProvider(sampler=sampler),
            options=HttpClientTelemetryOptions(captured_request_headers=["x-a"]),
        )

        telemetry.start(HttpClientRequest(method="GET", url="https://example.com", headers={"X-A": "1"})).end()

        self.assertEqual(
            sampler.attributes,
            [{**_BASE_ATTRIBUTES, URL_FULL: "https://example.com", "http.request.header.x-a": ("1",)}],
        )

    def test_response_headers(self) -> None:
        telemetry = self._telemetry(
            HttpClientTelemetryOptions(
                captured_response_headers=["content-type", "set-cookie"],
                sanitized_headers=["Set-Cookie"],
            )
        )

        operation = telemetry.start(
            HttpClientRequest(method="GET", url="https://example.com", headers={"Content-Type": "text/plain"})
        )
        operation.set_response(
            HttpClientResponse(
                status_code=200,
                headers={"Content-Type": "application/json", "Set-Cookie": ["a=1", "b=2"], "Server": "test"},
            )
        )
        operation.end()

        (span,) = self.get_finished_spans()
        self.assertEqual(
            dict(span.attributes or {}),
            {
                **_BASE_ATTRIBUTES,
                HTTP_RESPONSE_STATUS_CODE: 200,
                URL_FULL: "https://example.com",
                "http.response.header.content-type": ("application/json",),
                "http.response.header.set-cookie": ("[REDACTED]", "[REDACTED]"),
            },
        )

    def test_set_response_after_end_records_nothing(self) -> None:
        telemetry = self._telemetry(HttpClientTelemetryOptions(captured_response_headers=["x-a"]))
        operation = telemetry.start(HttpClientRequest(method="GET", url="https://example.com"))
        operation.end()

        operation.set_response(HttpClientResponse(headers={"X-A": "1"}))

        (span,) = self.get_finished_spans()
        self.assertEqual(dict(span.attributes or {}), {**_BASE_ATTRIBUTES, URL_FULL: "https://example.com"})

    def test_set_response_on_skipped_operation(self) -> None:
        telemetry = self._telemetry(
            HttpClientTelemetryOptions(
                captured_request_headers=["x-a"],
                captured_response_headers=["x-a"],
                excluded_urls=["https://example.com"],
            )
        )
        operation = telemetry.start(HttpClientRequest(method="GET", url="https://example.com", headers={"X-A": "1"}))

        operation.set_response(HttpClientResponse(headers={"X-A": "1"}))
        operation.end()

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(self.get_finished_spans(), [])
