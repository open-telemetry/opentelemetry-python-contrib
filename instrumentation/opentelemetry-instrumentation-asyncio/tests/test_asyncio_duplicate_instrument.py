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

"""
A general test verifying that when the same Future objects (or coroutines) are
repeatedly instrumented (for example, via `trace_future`), callback references
do not leak. In this example, we mimic a typical scenario where a small set of
Futures might be reused throughout an application's lifecycle.
"""

import asyncio

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.test.test_base import TestBase


class TestAsyncioDuplicateInstrument(TestBase):
    """
    Tests whether repeated instrumentation of the same Futures leads to
    exponential callback growth (potential memory leak).
    """

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.instrumentor = AsyncioInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        self.loop.close()
        asyncio.set_event_loop(None)
        super().tearDown()

    def test_duplicate_instrumentation_of_futures(self):
        """
        If instrumentor.trace_future is called multiple times on the same Future,
        we should NOT see an unbounded accumulation of callbacks.
        """
        fut1 = asyncio.Future()
        fut2 = asyncio.Future()

        num_iterations = 10
        for _ in range(num_iterations):
            self.instrumentor.trace_future(fut1)
            self.instrumentor.trace_future(fut2)

        self.assertLessEqual(
            len(fut1._callbacks),
            1,
            f"fut1 has {len(fut1._callbacks)} callbacks. Potential leak!"
        )
        self.assertLessEqual(
            len(fut2._callbacks),
            1,
            f"fut2 has {len(fut2._callbacks)} callbacks. Potential leak!"
        )
