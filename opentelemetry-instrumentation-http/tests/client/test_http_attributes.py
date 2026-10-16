# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from tests._util import RecordingSampler, assert_attributes

from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientResponse,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_REQUEST_METHOD_ORIGINAL,
    HTTP_REQUEST_RESEND_COUNT,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.test.test_base import TestBase

_URL = "https://example.com"
_ALL_SIZES_OPTIONS = HttpClientTelemetryDevelopmentOptions(
    capture_request_body_size=True,
    capture_request_size=True,
    capture_response_body_size=True,
    capture_response_size=True,
)


class TestHttpClientTelemetryHttpAttributes(TestBase):
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

    def _http_attributes(self) -> dict[str, Any]:
        (span,) = self.get_finished_spans()
        self.memory_exporter.clear()
        return {
            key: value
            for key, value in (span.attributes or {}).items()
            if key.startswith("http.") and not key.startswith(("http.request.header.", "http.response.header."))
        }

    def test_attributes(self) -> None:
        for case, options, development_options, request, response, expected in (
            (
                "known method",
                None,
                None,
                HttpClientRequest(method="QUERY", url=_URL),
                None,
                {HTTP_REQUEST_METHOD: "QUERY"},
            ),
            (
                "unknown method",
                None,
                None,
                HttpClientRequest(method="PURGE", url=_URL),
                None,
                {HTTP_REQUEST_METHOD: "_OTHER", HTTP_REQUEST_METHOD_ORIGINAL: "PURGE"},
            ),
            (
                "unknown method is case-sensitive",
                None,
                None,
                HttpClientRequest(method="GeT", url=_URL),
                None,
                {HTTP_REQUEST_METHOD: "_OTHER", HTTP_REQUEST_METHOD_ORIGINAL: "GeT"},
            ),
            (
                "capture all methods",
                HttpClientTelemetryOptions(capture_all_methods=True),
                None,
                HttpClientRequest(method="PURGE", url=_URL),
                None,
                {HTTP_REQUEST_METHOD: "PURGE"},
            ),
            (
                "status code",
                None,
                None,
                HttpClientRequest(method="GET", url=_URL),
                HttpClientResponse(status_code=404),
                {HTTP_REQUEST_METHOD: "GET", HTTP_RESPONSE_STATUS_CODE: 404},
            ),
            (
                "resend count",
                None,
                None,
                HttpClientRequest(method="GET", url=_URL, resend_count=2),
                None,
                {HTTP_REQUEST_METHOD: "GET", HTTP_REQUEST_RESEND_COUNT: 2},
            ),
            (
                "resend count zero",
                None,
                None,
                HttpClientRequest(method="GET", url=_URL, resend_count=0),
                None,
                {HTTP_REQUEST_METHOD: "GET"},
            ),
            (
                "sizes",
                None,
                _ALL_SIZES_OPTIONS,
                HttpClientRequest(method="GET", url=_URL, body_size=0, total_size=100),
                HttpClientResponse(body_size=20, total_size=200),
                {
                    HTTP_REQUEST_METHOD: "GET",
                    "http.request.body.size": 0,
                    "http.request.size": 100,
                    "http.response.body.size": 20,
                    "http.response.size": 200,
                },
            ),
        ):
            with self.subTest(case):
                operation = self._telemetry(options, development_options).start(request)
                if response is not None:
                    operation.set_response(response)
                operation.end()

                assert_attributes(self, self._http_attributes(), expected)

    def test_method_is_available_to_sampler(self) -> None:
        sampler = RecordingSampler()
        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test", tracer_provider=TracerProvider(sampler=sampler)
        )

        telemetry.start(HttpClientRequest(method="PURGE", url=_URL)).end()

        self.assertEqual(len(sampler.attributes), 1)
        self.assertEqual(sampler.attributes[0][HTTP_REQUEST_METHOD], "_OTHER")
        self.assertEqual(sampler.attributes[0][HTTP_REQUEST_METHOD_ORIGINAL], "PURGE")

    def test_sizes_are_opt_in(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL, body_size=10, total_size=100))
        operation.set_request_size(body_size=10, total_size=100)
        operation.set_response(HttpClientResponse(body_size=20, total_size=200))
        operation.end()

        self.assertEqual(self._http_attributes(), {HTTP_REQUEST_METHOD: "GET"})

    def test_set_request_size(self) -> None:
        operation = self._telemetry(development_options=_ALL_SIZES_OPTIONS).start(
            HttpClientRequest(method="GET", url=_URL, body_size=10)
        )
        operation.set_request_size(total_size=100)
        operation.set_request_size(body_size=15)
        operation.end()

        self.assertEqual(
            self._http_attributes(),
            {HTTP_REQUEST_METHOD: "GET", "http.request.body.size": 15, "http.request.size": 100},
        )

    def test_after_end_records_nothing(self) -> None:
        operation = self._telemetry(development_options=_ALL_SIZES_OPTIONS).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        operation.end()

        operation.set_request_size(body_size=10, total_size=100)
        operation.set_response(HttpClientResponse(status_code=200, body_size=20, total_size=200))

        self.assertEqual(self._http_attributes(), {HTTP_REQUEST_METHOD: "GET"})

    def test_skipped_operation(self) -> None:
        operation = self._telemetry(HttpClientTelemetryOptions(excluded_urls=[_URL]), _ALL_SIZES_OPTIONS).start(
            HttpClientRequest(method="GET", url=_URL, body_size=10)
        )

        operation.set_request_size(body_size=10)
        operation.set_response(HttpClientResponse(status_code=200, body_size=20))
        operation.end()

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(self.get_finished_spans(), [])
