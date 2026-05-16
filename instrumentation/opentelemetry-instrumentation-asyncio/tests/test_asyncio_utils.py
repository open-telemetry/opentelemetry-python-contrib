# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
    OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED,
)
from opentelemetry.instrumentation.asyncio.utils import (
    get_coros_to_trace,
    get_future_trace_enabled,
)


class TestAsyncioToThread(TestCase):
    @patch.dict(
        "os.environ",
        {
            OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE: "test1,test2,test3 ,test4"
        },
    )
    def test_separator(self):
        self.assertEqual(
            get_coros_to_trace(), {"test1", "test2", "test3", "test4"}
        )

    @patch.dict(
        "os.environ", {OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED: "true"}
    )
    def test_future_trace_enabled(self):
        self.assertEqual(get_future_trace_enabled(), True)
