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
