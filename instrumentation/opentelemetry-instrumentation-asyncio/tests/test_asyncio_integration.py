# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
