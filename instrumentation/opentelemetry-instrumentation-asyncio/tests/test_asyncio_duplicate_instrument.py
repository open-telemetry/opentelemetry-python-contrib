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


class MockSubscription:
    """
    Example class holding an unsubscribe_future, similar to something like
    aiokafka's subscription.
    """

    def __init__(self):
        self.unsubscribe_future = asyncio.Future()


class MockGroupCoordinator:
    """
    Example class modeling repeated instrumentation of the same Future objects.
    """

    def __init__(self):
        self._closing = asyncio.Future()
        self.subscription = MockSubscription()
        self._rejoin_needed_fut = asyncio.Future()

    async def run_routine(self, instrumentor):
        """
        Each time this routine is called, the same 3 Futures are 'traced' again.
        In a real-life scenario, there's often a loop reusing these objects.
        """
        instrumentor.trace_future(self._closing)
        instrumentor.trace_future(self.subscription.unsubscribe_future)
        instrumentor.trace_future(self._rejoin_needed_fut)


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
        coordinator = MockGroupCoordinator()

        # Simulate calling the routine multiple times
        num_iterations = 10
        for _ in range(num_iterations):
            self.loop.run_until_complete(
                coordinator.run_routine(self.instrumentor)
            )

        # Check for callback accumulation
        closing_cb_count = len(coordinator._closing._callbacks)
        unsub_cb_count = len(
            coordinator.subscription.unsubscribe_future._callbacks
        )
        rejoin_cb_count = len(coordinator._rejoin_needed_fut._callbacks)

        # If instrumentation is properly deduplicated, each Future might have ~1-2 callbacks.
        max_expected_callbacks = 2
        self.assertLessEqual(
            closing_cb_count,
            max_expected_callbacks,
            f"_closing Future has {closing_cb_count} callbacks. Potential leak!",
        )
        self.assertLessEqual(
            unsub_cb_count,
            max_expected_callbacks,
            f"unsubscribe_future has {unsub_cb_count} callbacks. Potential leak!",
        )
        self.assertLessEqual(
            rejoin_cb_count,
            max_expected_callbacks,
            f"_rejoin_needed_fut has {rejoin_cb_count} callbacks. Potential leak!",
        )
