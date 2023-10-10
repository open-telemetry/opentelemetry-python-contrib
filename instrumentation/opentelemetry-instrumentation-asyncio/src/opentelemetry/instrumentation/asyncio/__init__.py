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

The opentelemetry-instrumentation-asycnio package allows tracing asyncio applications.
The metric for coroutine, future, is generated even if there is no setting to generate a span.


Set the name of the coroutine you want to trace.
-------------------------------------------------
.. code::
    export OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE=coro_name,coro_name2,coro_name3

If you want to keep track of which function to use in the to_thread function of asyncio, set the name of the function.
------------------------------------------------------------------------------------------------------------------------
.. code::
    export OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE=func_name,func_name2,func_name3

For future, set it up like this
---------------------------------
.. code::
    export OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED=true

Run instrumented application
------------------------------
1. coroutine
----------------
.. code:: python

    # export OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE=sleep

    import asyncio
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

    AsyncioInstrumentor().instrument()

    async def main():
        await asyncio.create_task(asyncio.sleep(0.1))

    asyncio.run(main())

2. future
------------
.. code:: python

    # export OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED=true

    loop = asyncio.get_event_loop()

    future = asyncio.Future()
    future.set_result(1)
    task = asyncio.ensure_future(future)
    loop.run_until_complete(task)

3. to_thread
-------------
.. code:: python

    # export OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE=func

    import asyncio
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

    AsyncioInstrumentor().instrument()

    async def main():
        await asyncio.to_thread(func)

    def func():
        pass

    asyncio.run(main())


asyncio metric types
---------------------

* `asyncio.futures.duration` (ms) - Duration of the future
* `asyncio.futures.exceptions` (count) - Number of exceptions raised by the future
* `asyncio.futures.cancelled` (count) - Number of futures cancelled
* `asyncio.futures.created` (count) - Number of futures created
* `asyncio.futures.active` (count) - Number of futures active
* `asyncio.futures.finished` (count) - Number of futures finished
* `asyncio.futures.timeouts` (count) - Number of futures timed out

* `asyncio.coroutine.duration` (ms) - Duration of the coroutine
* `asyncio.coroutine.exceptions` (count) - Number of exceptions raised by the coroutine
* `asyncio.coroutine.created` (count) - Number of coroutines created
* `asyncio.coroutine.active` (count) - Number of coroutines active
* `asyncio.coroutine.finished` (count) - Number of coroutines finished
* `asyncio.coroutine.timeouts` (count) - Number of coroutines timed out
* `asyncio.coroutine.cancelled` (count) - Number of coroutines cancelled

* `asyncio.to_thread.duration` (ms) - Duration of the to_thread
* `asyncio.to_thread.exceptions` (count) - Number of exceptions raised by the to_thread
* `asyncio.to_thread.created` (count) - Number of to_thread created
* `asyncio.to_thread.active` (count) - Number of to_thread active
* `asyncio.to_thread.finished` (count) - Number of to_thread finished


API
---
"""
import asyncio
import sys
from asyncio import futures
from timeit import default_timer
from typing import Collection

from opentelemetry.metrics import get_meter
from opentelemetry.trace import get_tracer
from opentelemetry.trace.status import Status, StatusCode
from wrapt import wrap_function_wrapper as _wrap

from opentelemetry.instrumentation.asyncio.metrics import *
from opentelemetry.instrumentation.asyncio.package import _instruments
from opentelemetry.instrumentation.asyncio.utils import get_coros_to_trace, get_future_trace_enabled, \
    get_to_thread_to_trace
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
        self.to_thread_duration_metric = None
        self.to_thread_exception_metric = None
        self.to_thread_active_metric = None
        self.to_thread_created_metric = None
        self.to_thread_finished_metric = None

        self.coro_duration_metric = None
        self.coro_exception_metric = None
        self.coro_cancelled_metric = None
        self.coro_active_metric = None
        self.coro_created_metric = None
        self.coro_finished_metric = None
        self.coro_timeout_metric = None

        self.future_duration_metric = None
        self.future_exception_metric = None
        self.future_cancelled_metric = None
        self.future_active_metric = None
        self.future_created_metric = None
        self.future_finished_metric = None
        self.future_timeout_metric = None

        self._tracer = None
        self._meter = None
        self._coros_name_to_trace: set = set()
        self._to_thread_name_to_trace: set = set()
        self._future_active_enabled: bool = False

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = get_tracer(
            __name__, __version__, tracer_provider
        )
        self._meter = get_meter(
            __name__, __version__, kwargs.get("meter_provider")
        )

        self._coros_name_to_trace = get_coros_to_trace()
        self._future_active_enabled = get_future_trace_enabled()
        self._to_thread_name_to_trace = get_to_thread_to_trace()

        self.create_coro_metric()
        self.create_future_metric()
        self.create_to_thread_metric()

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
                wrapped_first_arg = self.trace_to_thread(first_arg)
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

    def trace_to_thread(self, func):
        """Trace a function."""
        start = default_timer()
        self.to_thread_created_metric.add(1)
        self.to_thread_active_metric.add(1)
        span = self._tracer.start_span(
            f"{ASYNCIO_PREFIX}to_thread_func-" + func.__name__) if func.__name__ in self._to_thread_name_to_trace else None
        exception = None
        try:
            return func
        except Exception as exc:
            exception_attr = {ASYNCIO_EXCEPTIONS_NAME: exc.__class__.__name__}
            exception = exc
            self.to_thread_exception_metric.add(1, exception_attr)
            raise
        finally:
            duration = max(round((default_timer() - start) * 1000), 0)
            self.to_thread_duration_metric.record(duration)
            self.to_thread_finished_metric.add(1)
            self.to_thread_active_metric.add(-1)
            if span:
                if span.is_recording() and exception:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(exception)
                span.end()

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
        start = default_timer()
        coro_attr = {
            ASYNCIO_COROUTINE_NAME: coro.__name__,
        }
        self.coro_created_metric.add(1, coro_attr)
        self.coro_active_metric.add(1, coro_attr)

        span = self._tracer.start_span(
            f"{ASYNCIO_PREFIX}coro-" + coro.__name__) if coro.__name__ in self._coros_name_to_trace else None

        exception = None
        try:
            return await coro
        # CancelledError is raised when a coroutine is cancelled
        # before it has a chance to run. We don't want to record
        # this as an error.
        except asyncio.CancelledError:
            self.coro_cancelled_metric.add(1, coro_attr)
        except asyncio.TimeoutError:
            self.coro_timeout_metric.add(1, coro_attr)
            raise
        except Exception as exc:
            exception = exc
            coro_exception_attr = coro_attr.copy()
            coro_exception_attr[ASYNCIO_EXCEPTIONS_NAME] = exc.__class__.__name__
            self.coro_exception_metric.add(1, coro_exception_attr)
            raise
        finally:
            duration = max(round((default_timer() - start) * 1000), 0)
            self.coro_duration_metric.record(duration, coro_attr)
            self.coro_finished_metric.add(1, coro_attr)
            self.coro_active_metric.add(-1, coro_attr)

            if span:
                if span.is_recording() and exception:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(exception)
                span.end()

    def trace_future(self, future):
        start = default_timer()
        self.future_created_metric.add(1)
        self.future_active_metric.add(1)
        span = self._tracer.start_span(f"{ASYNCIO_PREFIX}future") if self._future_active_enabled else None

        def callback(f):
            exception = f.exception()
            if isinstance(exception, asyncio.CancelledError):
                self.future_cancelled_metric.add(1)
            elif isinstance(exception, asyncio.TimeoutError):
                self.future_timeout_metric.add(1)
            elif exception:
                exception_attr = {ASYNCIO_EXCEPTIONS_NAME: exception.__class__.__name__}
                self.future_exception_metric.add(1, exception_attr)

            duration = max(round((default_timer() - start) * 1000), 0)
            self.future_duration_metric.record(duration)
            self.future_finished_metric.add(1)
            self.future_active_metric.add(-1)
            if span:
                if span.is_recording() and exception:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(exception)
                span.end()

        future.add_done_callback(callback)
        return future

    def create_coro_metric(self):
        self.coro_duration_metric = self._meter.create_histogram(
            name=ASYNCIO_COROUTINE_DURATION,
            description="Duration of asyncio coroutine",
            unit="ms",
        )
        self.coro_exception_metric = self._meter.create_counter(
            name=ASYNCIO_COROUTINE_EXCEPTIONS,
            description="Number of exceptions in asyncio coroutine",
            unit="1",
        )
        self.coro_cancelled_metric = self._meter.create_counter(
            name=ASYNCIO_COROUTINE_CANCELLED,
            description="Number of asyncio coroutine cancelled",
            unit="1",
        )
        self.coro_active_metric = self._meter.create_up_down_counter(
            name=ASYNCIO_COROUTINE_ACTIVE,
            description="Number of asyncio coroutine active",
            unit="1",
        )
        self.coro_created_metric = self._meter.create_counter(
            name=ASYNCIO_COROUTINE_CREATED,
            description="Number of asyncio coroutine created",
            unit="1",
        )
        self.coro_finished_metric = self._meter.create_counter(
            name=ASYNCIO_COROUTINE_FINISHED,
            description="Number of asyncio coroutine finished",
            unit="1",
        )
        self.coro_timeout_metric = self._meter.create_counter(
            name=ASYNCIO_COROUTINE_TIMEOUTS,
            description="Number of asyncio coroutine timeouts",
            unit="1",
        )

    def create_future_metric(self):
        self.future_duration_metric = self._meter.create_histogram(
            name=ASYNCIO_FUTURES_DURATION,
            description="Duration of asyncio future",
            unit="ms",
        )
        self.future_exception_metric = self._meter.create_counter(
            name=ASYNCIO_FUTURES_EXCEPTIONS,
            description="Number of exceptions in asyncio future",
            unit="1",
        )
        self.future_cancelled_metric = self._meter.create_counter(
            name=ASYNCIO_FUTURES_CANCELLED,
            description="Number of asyncio future cancelled",
            unit="1",
        )
        self.future_created_metric = self._meter.create_counter(
            name=ASYNCIO_FUTURES_CREATED,
            description="Number of asyncio future created",
            unit="1",
        )
        self.future_active_metric = self._meter.create_up_down_counter(
            name=ASYNCIO_FUTURES_ACTIVE,
            description="Number of asyncio future active",
            unit="1",
        )
        self.future_finished_metric = self._meter.create_counter(
            name=ASYNCIO_FUTURES_FINISHED,
            description="Number of asyncio future finished",
            unit="1",
        )
        self.future_timeout_metric = self._meter.create_counter(
            name=ASYNCIO_FUTURES_TIMEOUTS,
            description="Number of asyncio future timeouts",
            unit="1",
        )

    def create_to_thread_metric(self):
        self.to_thread_duration_metric = self._meter.create_histogram(
            name=ASYNCIO_TO_THREAD_DURATION,
            description="Duration of asyncio function",
            unit="ms",
        )
        self.to_thread_exception_metric = self._meter.create_counter(
            name=ASYNCIO_TO_THREAD_EXCEPTIONS,
            description="Number of exceptions in asyncio function",
            unit="1",
        )
        self.to_thread_created_metric = self._meter.create_counter(
            name=ASYNCIO_TO_THREAD_CREATED,
            description="Number of asyncio function created",
            unit="1",
        )
        self.to_thread_active_metric = self._meter.create_up_down_counter(
            name=ASYNCIO_TO_THREAD_ACTIVE,
            description="Number of asyncio function active",
            unit="1",
        )
        self.to_thread_finished_metric = self._meter.create_counter(
            name=ASYNCIO_TO_THREAD_FINISHED,
            description="Number of asyncio function finished",
            unit="1",
        )
