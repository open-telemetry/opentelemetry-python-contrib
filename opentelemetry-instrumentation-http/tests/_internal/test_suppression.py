# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from contextlib import AbstractContextManager, nullcontext
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.context import (
    _SUPPRESS_HTTP_INSTRUMENTATION_KEY,
    _SUPPRESS_INSTRUMENTATION_KEY,
    Context,
    set_value,
)
from opentelemetry.instrumentation.http._internal import _suppression
from opentelemetry.instrumentation.http._internal._suppression import (
    is_http_instrumentation_suppressed,
)


class TestIsHttpInstrumentationSuppressed(TestCase):
    def test_is_http_instrumentation_suppressed(self) -> None:
        for unavailable_key, values, expected in (
            (None, {}, False),
            (None, {_SUPPRESS_INSTRUMENTATION_KEY: True}, True),
            (None, {_SUPPRESS_HTTP_INSTRUMENTATION_KEY: True}, True),
            (None, {_SUPPRESS_INSTRUMENTATION_KEY: False, _SUPPRESS_HTTP_INSTRUMENTATION_KEY: False}, False),
            # A plain string key is ignored.
            (None, {"suppress_instrumentation": True}, False),
            # A key that the API no longer provides is skipped.
            ("_SUPPRESS_INSTRUMENTATION_KEY", {_SUPPRESS_INSTRUMENTATION_KEY: True}, False),
            ("_SUPPRESS_INSTRUMENTATION_KEY", {_SUPPRESS_HTTP_INSTRUMENTATION_KEY: True}, True),
            ("_SUPPRESS_HTTP_INSTRUMENTATION_KEY", {_SUPPRESS_HTTP_INSTRUMENTATION_KEY: True}, False),
            ("_SUPPRESS_HTTP_INSTRUMENTATION_KEY", {_SUPPRESS_INSTRUMENTATION_KEY: True}, True),
        ):
            with self.subTest(unavailable_key=unavailable_key, values=values):
                context = Context()
                for key, value in values.items():
                    context = set_value(key, value, context)
                unavailable: AbstractContextManager[Any] = (
                    patch.object(_suppression, unavailable_key, None) if unavailable_key else nullcontext()
                )

                with unavailable:
                    self.assertIs(is_http_instrumentation_suppressed(context), expected)
