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
.. asyncio: https://github.com/python/asyncio

Usage
-----

.. code-block:: python

    import asyncio
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

    AsyncioInstrumentor().instrument()

    async def main():
        await asyncio.create_task(asyncio.sleep(0.1))

    asyncio.run(main())

API
---
"""
import asyncio
import sys
from asyncio import futures
from typing import Collection

from opentelemetry.trace import get_tracer
from opentelemetry.trace.status import Status, StatusCode
from wrapt import wrap_function_wrapper as _wrap

from opentelemetry.instrumentation.asyncio.package import _instruments
from opentelemetry.instrumentation.asyncio.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap

ASYNCIO_PREFIX = "asyncio."


class AsyncioInstrumentor(BaseInstrumentor):
    """
    An instrumentor for asyncio

    See `BaseInstrumentor`
    """

    methods_with_coroutine = [
        "create_task",
        "ensure_future",
        "wait_for",
        "wait",
        "as_completed",
        "run_coroutine_threadsafe",
    ]

    def __init__(self):
        super().__init__()
        self._tracer = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = get_tracer(
            __name__, __version__, tracer_provider
        )
        for method in self.methods_with_coroutine:
            self.instrument_method_with_coroutine(method)

        self.instrument_gather()
        self.instrument_to_thread()
        self.instrument_taskgroup_create_task()

    def _uninstrument(self, **kwargs):
        for method in self.methods_with_coroutine:
            self.uninstrument_method_with_coroutine(method)
        self.uninstrument_gather()
        self.uninstrument_to_thread()
        self.uninstrument_taskgroup_create_task()

    def instrument_method_with_coroutine(self, method_name):
        """
        Instruments specified asyncio method.
        """

        def wrap_coro_or_future(method, instance, args, kwargs):

            # If the first argument is a coroutine or future,
            # we decorate it with a span and return the task.
            if args and len(args) > 0:
                first_arg = args[0]
                # Check if it's a coroutine or future and wrap it
                if asyncio.iscoroutine(first_arg) or futures.isfuture(first_arg):
                    args = (self.trace_item(first_arg),) + args[1:]
                # Check if it's a list and wrap each item
                elif isinstance(first_arg, list):
                    args = ([self.trace_item(item) for item in first_arg],) + args[1:]
            return method(*args, **kwargs)

        _wrap(asyncio, method_name, wrap_coro_or_future)

    def uninstrument_method_with_coroutine(self, method_name):
        """
        Uninstrument specified asyncio method.
        """
        unwrap(asyncio, method_name)

    def instrument_gather(self):

        def wrap_coros_or_futures(method, instance, args, kwargs):
            if args and len(args) > 0:
                # Check if it's a coroutine or future and wrap it
                wrapped_args = tuple(self.trace_item(item) for item in args)
                return method(*wrapped_args, **kwargs)

        _wrap(asyncio, "gather", wrap_coros_or_futures)

    def uninstrument_gather(self):
        unwrap(asyncio, "gather")

    def instrument_to_thread(self):
        # to_thread was added in Python 3.9
        if sys.version_info < (3, 9):
            return

        def wrap_to_thread(method, instance, args, kwargs):
            if args:
                first_arg = args[0]
                # Wrap the first argument
                wrapped_first_arg = self.trace_func(first_arg)
                wrapped_args = (wrapped_first_arg,) + args[1:]

                return method(*wrapped_args, **kwargs)

        _wrap(asyncio, "to_thread", wrap_to_thread)

    def uninstrument_to_thread(self):
        # to_thread was added in Python 3.9
        if sys.version_info < (3, 9):
            return
        unwrap(asyncio, "to_thread")

    def instrument_taskgroup_create_task(self):
        # TaskGroup.create_task was added in Python 3.11
        if sys.version_info < (3, 11):
            return

        def wrap_taskgroup_create_task(method, instance, args, kwargs):
            if args:
                coro = args[0]
                wrapped_coro = self.trace_coroutine(coro)
                wrapped_args = (wrapped_coro,) + args[1:]
                return method(*wrapped_args, **kwargs)

        _wrap(asyncio.TaskGroup, "create_task", wrap_taskgroup_create_task)

    def uninstrument_taskgroup_create_task(self):
        # TaskGroup.create_task was added in Python 3.11
        if sys.version_info < (3, 11):
            return
        unwrap(asyncio.TaskGroup, "create_task")

    def trace_func(self, func):
        """Trace a function."""
        with self._tracer.start_as_current_span(f"{ASYNCIO_PREFIX}to_thread_func-" + func.__name__) as span:
            try:
                return func
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exc)
                raise

    def trace_item(self, coro_or_future):
        """Trace a coroutine or future item."""
        # Task is already traced, return it
        if isinstance(coro_or_future, asyncio.Task):
            return coro_or_future
        if asyncio.iscoroutine(coro_or_future):
            return self.trace_coroutine(coro_or_future)
        elif futures.isfuture(coro_or_future):
            return self.trace_future(coro_or_future)
        return coro_or_future

    async def trace_coroutine(self, coro):

        with self._tracer.start_as_current_span(f"{ASYNCIO_PREFIX}coro-" + coro.__name__) as span:
            exception = None  # Initialize the exception variable
            try:
                return await coro
            # CancelledError is raised when a coroutine is cancelled
            # before it has a chance to run. We don't want to record
            # this as an error.
            except asyncio.CancelledError:
                pass
            except (asyncio.TimeoutError,
                    asyncio.InvalidStateError,
                    asyncio.SendfileNotAvailableError,
                    asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError,
                    asyncio.BrokenBarrierError,
                    Exception) as exc:  # General exception should be the last
                exception = exc
                raise
            finally:
                if span.is_recording() and exception:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(exception)

    def trace_future(self, future):
        span = self._tracer.start_span(f"{ASYNCIO_PREFIX}" + future.__class__.__name__)

        def callback(f):
            exception = f.exception()
            if exception:
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exception)
            span.end()

        future.add_done_callback(callback)
        return future
