# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from typing import Any, cast

from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientResponse,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode

_URL = "https://example.com"
_IGNORE_CANCELLATIONS_OPTIONS = HttpClientTelemetryDevelopmentOptions(ignore_cancellation_errors=True)


class _CustomError(Exception):
    pass


class _ErrorsTestBase(TestBase):
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

    def _span(self) -> ReadableSpan:
        (span,) = self.get_finished_spans()
        return span

    def _end(
        self,
        status_code: int | None,
        end_kwargs: dict[str, Any],
        development_options: HttpClientTelemetryDevelopmentOptions | None = None,
    ) -> None:
        operation = self._telemetry(development_options=development_options).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        if status_code is not None:
            operation.set_response(HttpClientResponse(status_code=status_code))
        operation.end(**end_kwargs)

    def _assert_outcome(self, span: ReadableSpan, expected: tuple[str, str | None, int] | None) -> None:
        if expected is None:
            self._assert_success(span)
        else:
            self._assert_error(span, *expected)

    def _assert_success(self, span: ReadableSpan) -> None:
        self.assertIs(span.status.status_code, StatusCode.UNSET)
        self.assertIsNone(span.status.description)
        self.assertNotIn(ERROR_TYPE, span.attributes or {})
        self.assertEqual(span.events, ())

    def _assert_error(
        self, span: ReadableSpan, error_type: str, description: str | None, exception_events: int
    ) -> None:
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, description)
        self.assertEqual((span.attributes or {})[ERROR_TYPE], error_type)
        self.assertIsInstance((span.attributes or {})[ERROR_TYPE], str)
        self.assertEqual([event.name for event in span.events], ["exception"] * exception_events)


class TestHttpClientTelemetryErrors(_ErrorsTestBase):
    def test_end(self) -> None:
        for case, status_code, end_kwargs, expected in (
            ("no response", None, {}, None),
            ("informational", 100, {}, None),
            ("ok", 200, {}, None),
            ("no content", 204, {}, None),
            ("redirect", 302, {}, None),
            ("last non-error", 399, {}, None),
            ("bad request", 400, {}, ("400", None, 0)),
            ("not found", 404, {}, ("404", None, 0)),
            ("server error", 500, {}, ("500", None, 0)),
            ("unavailable", 503, {}, ("503", None, 0)),
            ("below 100", 99, {}, ("99", None, 0)),
            ("600 and above", 600, {}, ("600", None, 0)),
            ("exception with empty message", None, {"exception": TimeoutError()}, ("TimeoutError", None, 1)),
            (
                "exception after success response",
                200,
                {"exception": ConnectionResetError("reset while reading body")},
                ("ConnectionResetError", "reset while reading body", 1),
            ),
            (
                "exception after error response",
                503,
                {"exception": ConnectionResetError("reset")},
                ("503", "reset", 1),
            ),
            ("error type without exception", None, {"error_type": "timeout"}, ("timeout", None, 0)),
            (
                "error status code takes precedence over error type",
                503,
                {"error_type": "timeout"},
                ("503", None, 0),
            ),
            (
                "error type takes precedence over exception",
                None,
                {"exception": TimeoutError("timed out"), "error_type": "timeout"},
                ("timeout", "timed out", 1),
            ),
        ):
            with self.subTest(case):
                self._end(status_code, end_kwargs)

                self._assert_outcome(self._span(), expected)
                self.memory_exporter.clear()

    def test_exception_without_response(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.end(exception=_CustomError("connection refused"))

        span = self._span()
        self._assert_error(span, f"{__name__}._CustomError", "connection refused", 1)
        self.assertEqual(span.events[0].attributes["exception.type"], f"{__name__}._CustomError")

    def test_end_is_idempotent(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.end(exception=TimeoutError("timed out"))
        operation.end(exception=ConnectionResetError("reset"))

        self._assert_error(self._span(), "TimeoutError", "timed out", 1)

    def test_instrument_records_and_reraises(self) -> None:
        error = TimeoutError("timed out")

        with self.assertRaises(TimeoutError) as caught:
            with self._telemetry().instrument(HttpClientRequest(method="GET", url=_URL)):
                raise error

        self.assertIs(caught.exception, error)
        self._assert_error(self._span(), "TimeoutError", "timed out", 1)

    def test_skipped_operation(self) -> None:
        operation = self._telemetry(HttpClientTelemetryOptions(excluded_urls=[_URL])).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        operation.record_exception(TimeoutError("timed out"))
        operation.set_response(HttpClientResponse(status_code=503))
        operation.end(exception=TimeoutError("timed out"))

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(self.get_finished_spans(), [])


class TestHttpClientTelemetryCancellations(_ErrorsTestBase):
    def test_end(self) -> None:
        for case, development_options, status_code, end_kwargs, expected in (
            (
                "cancellations are errors by default",
                None,
                None,
                {"exception": asyncio.CancelledError()},
                ("asyncio.exceptions.CancelledError", None, 1),
            ),
            (
                "cancelled flag is ignored by default",
                None,
                None,
                {"error_type": "cancelled", "cancelled": True},
                ("cancelled", None, 0),
            ),
            (
                "ignore CancelledError",
                _IGNORE_CANCELLATIONS_OPTIONS,
                None,
                {"exception": asyncio.CancelledError()},
                None,
            ),
            ("ignore GeneratorExit", _IGNORE_CANCELLATIONS_OPTIONS, None, {"exception": GeneratorExit()}, None),
            ("ignore KeyboardInterrupt", _IGNORE_CANCELLATIONS_OPTIONS, None, {"exception": KeyboardInterrupt()}, None),
            (
                "ignore exception flagged as cancelled",
                _IGNORE_CANCELLATIONS_OPTIONS,
                None,
                {"exception": _CustomError("trio cancelled"), "cancelled": True},
                None,
            ),
            (
                "ignore error type flagged as cancelled",
                _IGNORE_CANCELLATIONS_OPTIONS,
                None,
                {"error_type": "cancelled", "cancelled": True},
                None,
            ),
            (
                "ignoring cancellations keeps error status code",
                _IGNORE_CANCELLATIONS_OPTIONS,
                503,
                {"exception": asyncio.CancelledError()},
                ("503", None, 0),
            ),
            (
                "ignoring cancellations records other errors",
                _IGNORE_CANCELLATIONS_OPTIONS,
                None,
                {"exception": TimeoutError("timed out")},
                ("TimeoutError", "timed out", 1),
            ),
        ):
            with self.subTest(case):
                self._end(status_code, end_kwargs, development_options)

                self._assert_outcome(self._span(), expected)
                self.memory_exporter.clear()

    def test_ignore_cancellation_errors_with_recorded_exception(self) -> None:
        operation = self._telemetry(development_options=_IGNORE_CANCELLATIONS_OPTIONS).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        operation.record_exception(asyncio.CancelledError())

        self.assertEqual(cast(ReadableSpan, operation.span).events, ())
        operation.end()

        self._assert_success(self._span())

    def test_recorded_cancellation_does_not_block_later_errors(self) -> None:
        operation = self._telemetry(development_options=_IGNORE_CANCELLATIONS_OPTIONS).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        operation.record_exception(asyncio.CancelledError())
        operation.record_exception(TimeoutError("timed out"))
        operation.end()

        self._assert_error(self._span(), "TimeoutError", "timed out", 1)


class TestHttpClientTelemetryRecordException(_ErrorsTestBase):
    def test_recorded_immediately(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.record_exception(TimeoutError("timed out"))

        span = cast(ReadableSpan, operation.span)
        self.assertEqual([event.name for event in span.events], ["exception"])
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual((span.attributes or {})[ERROR_TYPE], "TimeoutError")

        operation.end()

        self._assert_error(self._span(), "TimeoutError", "timed out", 1)

    def test_first_recording_wins(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.record_exception(TimeoutError("first"), error_type="timeout")
        operation.record_exception(ConnectionResetError("second"), error_type="reset")
        operation.end()

        self._assert_error(self._span(), "timeout", "first", 1)

    def test_end_arguments_are_ignored_after_recording(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.record_exception(TimeoutError("timed out"), error_type="timeout")
        operation.end(exception=ConnectionResetError("reset"), error_type="reset")

        self._assert_error(self._span(), "timeout", "timed out", 1)

    def test_error_response_after_recording(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.record_exception(TimeoutError("timed out"), error_type="timeout")
        operation.set_response(HttpClientResponse(status_code=503))
        operation.end()

        self._assert_error(self._span(), "503", "timed out", 1)

    def test_error_response_before_recording(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.set_response(HttpClientResponse(status_code=503))
        operation.record_exception(TimeoutError("timed out"))
        operation.end()

        self._assert_error(self._span(), "503", "timed out", 1)

    def test_success_response_after_recording(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.record_exception(TimeoutError("timed out"))
        operation.set_response(HttpClientResponse(status_code=200))
        operation.end()

        self._assert_error(self._span(), "TimeoutError", "timed out", 1)

    def test_after_end(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.end()
        operation.record_exception(TimeoutError("timed out"))

        self._assert_success(self._span())

    def test_skipped_operation(self) -> None:
        operation = self._telemetry(HttpClientTelemetryOptions(excluded_urls=[_URL])).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        operation.record_exception(TimeoutError("timed out"))
        operation.end()

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(self.get_finished_spans(), [])
