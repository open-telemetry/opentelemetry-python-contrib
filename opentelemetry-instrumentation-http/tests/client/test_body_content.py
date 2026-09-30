# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any
from unittest.mock import patch

from tests._util import CaseInsensitiveHeaders, assert_attributes

from opentelemetry.context import _SUPPRESS_HTTP_INSTRUMENTATION_KEY, set_value
from opentelemetry.instrumentation.http.client import (
    HttpClientOperation,
    HttpClientRequest,
    HttpClientResponse,
    HttpClientTelemetry,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.test.test_base import TestBase

_URL = "https://example.com"
_REQUEST_BODY = "http.request.body.content"
_RESPONSE_BODY = "http.response.body.content"
_JSON_CONTENT_TYPE = {"content-type": "application/json"}
_CAPTURE_ALL_OPTIONS = HttpClientTelemetryDevelopmentOptions(
    capture_request_body_content=True, capture_response_body_content=True
)


class TestHttpClientTelemetryBodyContent(TestBase):
    def _start(
        self,
        development_options: HttpClientTelemetryDevelopmentOptions | None = _CAPTURE_ALL_OPTIONS,
        headers: Mapping[str, str | Sequence[str]] | None = None,
    ) -> HttpClientOperation:
        return HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            development_options=development_options,
        ).start(HttpClientRequest(method="POST", url=_URL, headers=headers))

    def _body_attributes(self) -> dict[str, Any]:
        (span,) = self.get_finished_spans()
        self.memory_exporter.clear()
        return {key: value for key, value in (span.attributes or {}).items() if key.endswith(".body.content")}

    def test_body_content(self) -> None:
        case_insensitive = CaseInsensitiveHeaders({"Content-Type": "application/json"})
        for case, development_options, request_headers, request_chunks, response, response_chunks, expected in (
            (
                "not captured by default",
                None,
                _JSON_CONTENT_TYPE,
                (b"{}",),
                HttpClientResponse(status_code=200, headers=_JSON_CONTENT_TYPE),
                (b"{}",),
                {},
            ),
            (
                "request and response body",
                _CAPTURE_ALL_OPTIONS,
                _JSON_CONTENT_TYPE,
                (b'{"name": ', b'"otel"}'),
                HttpClientResponse(status_code=200, headers={"content-type": "text/html; charset=latin-1"}),
                ("<p>café</p>".encode("latin-1"),),
                {_REQUEST_BODY: '{"name": "otel"}', _RESPONSE_BODY: "<p>café</p>"},
            ),
            (
                "case-insensitive headers",
                _CAPTURE_ALL_OPTIONS,
                case_insensitive,
                (b"{}",),
                HttpClientResponse(status_code=200, headers=case_insensitive),
                (b"[]",),
                {_REQUEST_BODY: "{}", _RESPONSE_BODY: "[]"},
            ),
            (
                "only request body",
                HttpClientTelemetryDevelopmentOptions(capture_request_body_content=True),
                _JSON_CONTENT_TYPE,
                (b"{}",),
                HttpClientResponse(status_code=200, headers=_JSON_CONTENT_TYPE),
                (b"{}",),
                {_REQUEST_BODY: "{}"},
            ),
            (
                "only response body",
                HttpClientTelemetryDevelopmentOptions(capture_response_body_content=True),
                _JSON_CONTENT_TYPE,
                (b"{}",),
                HttpClientResponse(status_code=200, headers=_JSON_CONTENT_TYPE),
                (b"{}",),
                {_RESPONSE_BODY: "{}"},
            ),
            (
                "binary content is skipped",
                _CAPTURE_ALL_OPTIONS,
                {"content-type": "application/octet-stream"},
                (b"\x00\x01",),
                HttpClientResponse(status_code=200, headers={"content-type": "image/png"}),
                (b"\x89PNG",),
                {},
            ),
            (
                "missing content type is skipped",
                _CAPTURE_ALL_OPTIONS,
                None,
                (b"hello",),
                HttpClientResponse(status_code=200),
                (b"hello",),
                {},
            ),
            ("response body without set_response is skipped", _CAPTURE_ALL_OPTIONS, None, (), None, (b"{}",), {}),
            (
                "no chunks records nothing",
                _CAPTURE_ALL_OPTIONS,
                _JSON_CONTENT_TYPE,
                (),
                HttpClientResponse(status_code=200, headers=_JSON_CONTENT_TYPE),
                (),
                {},
            ),
            (
                "max size",
                HttpClientTelemetryDevelopmentOptions(
                    capture_request_body_content=True, capture_response_body_content=True, body_content_max_size=4
                ),
                {"content-type": "text/plain; charset=utf-8"},
                ("abcdé".encode(),),
                HttpClientResponse(status_code=200, headers={"content-type": "text/plain"}),
                ("abé".encode(), b"more"),
                {_REQUEST_BODY: "abcd", _RESPONSE_BODY: "abé"},
            ),
        ):
            with self.subTest(case):
                operation = self._start(development_options, request_headers)
                for chunk in request_chunks:
                    operation.add_request_body(chunk)
                if response is not None:
                    operation.set_response(response)
                for chunk in response_chunks:
                    operation.add_response_body(chunk)
                operation.end()

                assert_attributes(self, self._body_attributes(), expected)

    def test_not_enabled_by_experimental_attributes_env_var(self) -> None:
        env = {"OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY": "true"}
        with patch.dict(os.environ, env, clear=True):
            options = HttpClientTelemetryDevelopmentOptions.from_env()

        self.assertIsNone(options.capture_request_body_content)
        self.assertIsNone(options.capture_response_body_content)
        self.assertIsNone(options.body_content_max_size)

    def test_chunks_after_end_are_ignored(self) -> None:
        operation = self._start(headers=_JSON_CONTENT_TYPE)
        operation.set_response(HttpClientResponse(status_code=200, headers=_JSON_CONTENT_TYPE))
        operation.add_response_body(b"[1")
        operation.end()
        operation.add_response_body(b", 2]")

        self.assertEqual(self._body_attributes(), {_RESPONSE_BODY: "[1"})

    def test_recorded_with_error(self) -> None:
        operation = self._start(headers=_JSON_CONTENT_TYPE)
        operation.add_request_body(b"{}")
        operation.end(exception=ConnectionError("reset"))

        self.assertEqual(self._body_attributes(), {_REQUEST_BODY: "{}"})

    def test_undecodable_content_does_not_interrupt_end(self) -> None:
        for charset, expected in (("utf-16", {}), ("base64_codec", {_RESPONSE_BODY: "aGk="})):
            with self.subTest(charset=charset):
                operation = self._start()
                operation.set_response(
                    HttpClientResponse(status_code=200, headers={"content-type": f"text/plain; charset={charset}"})
                )
                operation.add_response_body(b"aGk=")
                operation.end(exception=ConnectionError("reset"))

                (span,) = self.get_finished_spans()
                self.assertEqual(span.attributes["error.type"], "ConnectionError")
                self.assertEqual(self._body_attributes(), expected)

    def test_non_textual_content_is_not_buffered(self) -> None:
        operation = self._start(headers={"content-type": "application/octet-stream"})
        self.assertIsNone(operation._request_body)  # pylint: disable=protected-access

        self.assertIsNotNone(operation._response_body)  # pylint: disable=protected-access
        operation.set_response(HttpClientResponse(status_code=200, headers={"content-type": "image/png"}))
        self.assertIsNone(operation._response_body)  # pylint: disable=protected-access
        operation.end()

    def test_suppressed_operation_is_noop(self) -> None:
        operation = HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            development_options=_CAPTURE_ALL_OPTIONS,
        ).start(
            HttpClientRequest(method="POST", url=_URL, headers=_JSON_CONTENT_TYPE),
            set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True),
        )
        operation.add_request_body(b"{}")
        operation.end()

        self.assertEqual(self.get_finished_spans(), [])

    def test_disabled_operation_has_no_captures(self) -> None:
        operation = self._start(development_options=None, headers=_JSON_CONTENT_TYPE)

        self.assertTrue(operation.span.is_recording())
        operation.end()
        self.assertIsNone(operation._request_body)  # pylint: disable=protected-access
        self.assertIsNone(operation._response_body)  # pylint: disable=protected-access

    def test_unsampled_operation_is_noop(self) -> None:
        operation = HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=TracerProvider(sampler=ALWAYS_OFF),
            development_options=_CAPTURE_ALL_OPTIONS,
        ).start(HttpClientRequest(method="POST", url=_URL, headers=_JSON_CONTENT_TYPE))
        operation.add_request_body(b"{}")
        operation.set_response(HttpClientResponse(status_code=200, headers=_JSON_CONTENT_TYPE))
        operation.add_response_body(b"{}")
        operation.end()

        self.assertFalse(operation.span.is_recording())
        self.assertIsNone(operation._request_body)  # pylint: disable=protected-access
        self.assertIsNone(operation._response_body)  # pylint: disable=protected-access
