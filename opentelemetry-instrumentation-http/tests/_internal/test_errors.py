# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from unittest import TestCase

from opentelemetry.instrumentation.http._internal._errors import (
    get_error_type,
    get_exception_type,
    is_cancellation,
    is_error_status_code,
)


class CustomError(Exception):
    class NestedError(Exception):
        pass


class TestIsErrorStatusCode(TestCase):
    def test_boundaries(self) -> None:
        for status_code, expected in (
            (0, True),
            (99, True),
            (100, False),
            (200, False),
            (399, False),
            (400, True),
            (499, True),
            (500, True),
            (599, True),
            (600, True),
        ):
            with self.subTest(status_code=status_code):
                self.assertIs(is_error_status_code(status_code), expected)


class TestGetExceptionType(TestCase):
    def test_get_exception_type(self) -> None:
        for exception, expected in (
            # Builtins are not qualified with their module.
            (ValueError(), "ValueError"),
            (TimeoutError(), "TimeoutError"),
            (CustomError(), f"{__name__}.CustomError"),
            (CustomError.NestedError(), f"{__name__}.CustomError.NestedError"),
            (asyncio.CancelledError(), "asyncio.exceptions.CancelledError"),
        ):
            with self.subTest(exception=type(exception)):
                self.assertEqual(get_exception_type(exception), expected)


class TestIsCancellation(TestCase):
    def test_is_cancellation(self) -> None:
        for exception, expected in (
            (asyncio.CancelledError(), True),
            (GeneratorExit(), True),
            (KeyboardInterrupt(), True),
            (None, False),
            (ValueError(), False),
            (TimeoutError(), False),
            (SystemExit(), False),
        ):
            with self.subTest(exception=type(exception)):
                self.assertIs(is_cancellation(exception), expected)


class TestGetErrorType(TestCase):
    def test_get_error_type(self) -> None:
        for status_code, error_type, exception, expected in (
            # No error.
            (None, None, None, None),
            (100, None, None, None),
            (200, None, None, None),
            (302, None, None, None),
            # An error status code takes precedence.
            (503, "timeout", ValueError(), "503"),
            (404, None, None, "404"),
            (99, None, None, "99"),
            # Then the error type.
            (200, "timeout", ValueError(), "timeout"),
            (None, "timeout", None, "timeout"),
            (None, "", ValueError(), "_OTHER"),
            # Then the exception type.
            (None, None, ValueError(), "ValueError"),
            (200, None, CustomError(), f"{__name__}.CustomError"),
        ):
            with self.subTest(status_code=status_code, error_type=error_type, exception=type(exception)):
                self.assertEqual(get_error_type(status_code, error_type, exception), expected)
