import asyncio

import pytest
from opentelemetry.test.test_base import TestBase


class TestTraceFuture(TestBase):

    @pytest.mark.asyncio
    def test_trace_future_cancelled(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        future = asyncio.Future()
        future.cancel()

        def callback(f):
            state = "cancelled" if f.cancelled() else "done"
            self.assertEqual(state, "cancelled")

        future.add_done_callback(callback)

        try:
            loop.run_until_complete(future)
        except asyncio.CancelledError as e:
            self.assertEqual(
                isinstance(e, asyncio.CancelledError), True
            )
