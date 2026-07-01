# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from .common_test_func import ensure_future


class TestAsyncioInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = get_tracer(
            __name__,
        )

    @patch.dict(
        "os.environ", {OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE: "sleep"}
    )
    def test_asyncio_integration(self):
        AsyncioInstrumentor().instrument()

        asyncio.run(ensure_future())
        spans = self.memory_exporter.get_finished_spans()
        self.memory_exporter.clear()
        assert spans
        AsyncioInstrumentor().uninstrument()

        asyncio.run(ensure_future())
        spans = self.memory_exporter.get_finished_spans()
        assert not spans
