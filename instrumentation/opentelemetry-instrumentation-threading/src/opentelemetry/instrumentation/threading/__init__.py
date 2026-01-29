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
Instrument threading to propagate OpenTelemetry context.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.threading import ThreadingInstrumentor

    ThreadingInstrumentor().instrument()

This library provides instrumentation for the `threading` module to ensure that
the OpenTelemetry context is propagated across threads. It is important to note
that this instrumentation does not produce any telemetry data on its own. It
merely ensures that the context is correctly propagated when threads are used.


When instrumented, new threads created using threading.Thread, threading.Timer,
or within futures.ThreadPoolExecutor will have the current OpenTelemetry
context attached, and this context will be re-activated in the thread's
run method or the executor's worker thread."
"""

from __future__ import annotations

import threading
from concurrent import futures
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable, Collection

from opentelemetry.metrics import get_meter
from wrapt import (
    wrap_function_wrapper,  # type: ignore[reportUnknownVariableType]
)

from opentelemetry import context
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.threading.package import _instruments
from opentelemetry.instrumentation.threading.version import __version__
from opentelemetry.instrumentation.utils import unwrap

if TYPE_CHECKING:
    from typing import Protocol, TypeVar

    R = TypeVar("R")

    class HasOtelContext(Protocol):
        _otel_context: context.Context


class ThreadingInstrumentor(BaseInstrumentor):
    __WRAPPER_START_METHOD = "start"
    __WRAPPER_RUN_METHOD = "run"
    __WRAPPER_SUBMIT_METHOD = "submit"
    __WRAPPER_INIT_METHOD = "__init__"

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url="https://opentelemetry.io/schemas/1.38.0",
        )

        self.working_items_count = meter.create_up_down_counter(
            name="python.threadpool.working_items.count",
            unit="threads",
            description="The number of jobs currently being processed by the thread pool",
        )
        self.queue_count = meter.create_up_down_counter(
            name="python.threadpool.queue.length",
            unit="threads",
            description="The number of jobs currently queued in the thread pool",
        )
        self.thread_count = meter.create_gauge(
            name="python.threadpool.thread.count",
            unit="threads",
            description="The maximum number of concurrent jobs allowed in the thread pool",
        )
        self.max_thread_count = meter.create_gauge(
            name="python.threadpool.thread.max_count",
            unit="threads",
            description="The maximum number of concurrent jobs allowed in the thread pool",
        )
        self._instrument_thread()
        self._instrument_timer()
        self._instrument_thread_pool()

    def _uninstrument(self, **kwargs: Any):
        self._uninstrument_thread()
        self._uninstrument_timer()
        self._uninstrument_thread_pool()

    @staticmethod
    def _instrument_thread():
        wrap_function_wrapper(
            threading.Thread,
            ThreadingInstrumentor.__WRAPPER_START_METHOD,
            ThreadingInstrumentor.__wrap_threading_start,
        )
        wrap_function_wrapper(
            threading.Thread,
            ThreadingInstrumentor.__WRAPPER_RUN_METHOD,
            ThreadingInstrumentor.__wrap_threading_run,
        )

    @staticmethod
    def _instrument_timer():
        wrap_function_wrapper(
            threading.Timer,
            ThreadingInstrumentor.__WRAPPER_START_METHOD,
            ThreadingInstrumentor.__wrap_threading_start,
        )
        wrap_function_wrapper(
            threading.Timer,
            ThreadingInstrumentor.__WRAPPER_RUN_METHOD,
            ThreadingInstrumentor.__wrap_threading_run,
        )

    def _instrument_thread_pool(self):
        wrap_function_wrapper(
            futures.ThreadPoolExecutor,
            ThreadingInstrumentor.__WRAPPER_INIT_METHOD,
            self.__build_wrap_thread_pool_init(),
        )
        wrap_function_wrapper(
            futures.ThreadPoolExecutor,
            ThreadingInstrumentor.__WRAPPER_SUBMIT_METHOD,
            self.__build_wrap_thread_pool_submit(),
        )

    @staticmethod
    def _uninstrument_thread():
        unwrap(threading.Thread, ThreadingInstrumentor.__WRAPPER_START_METHOD)
        unwrap(threading.Thread, ThreadingInstrumentor.__WRAPPER_RUN_METHOD)

    @staticmethod
    def _uninstrument_timer():
        unwrap(threading.Timer, ThreadingInstrumentor.__WRAPPER_START_METHOD)
        unwrap(threading.Timer, ThreadingInstrumentor.__WRAPPER_RUN_METHOD)

    @staticmethod
    def _uninstrument_thread_pool():
        unwrap(
            futures.ThreadPoolExecutor,
            ThreadingInstrumentor.__WRAPPER_INIT_METHOD,
        )
        unwrap(
            futures.ThreadPoolExecutor,
            ThreadingInstrumentor.__WRAPPER_SUBMIT_METHOD,
        )

    @staticmethod
    def __wrap_threading_start(
        call_wrapped: Callable[[], None],
        instance: HasOtelContext,
        args: tuple[()],
        kwargs: dict[str, Any],
    ) -> None:
        instance._otel_context = context.get_current()
        return call_wrapped(*args, **kwargs)

    @staticmethod
    def __wrap_threading_run(
        call_wrapped: Callable[..., R],
        instance: HasOtelContext,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> R:
        token = None
        try:
            token = context.attach(instance._otel_context)
            return call_wrapped(*args, **kwargs)
        finally:
            if token is not None:
                context.detach(token)

    def __build_wrap_thread_pool_submit(self) -> Callable[..., Future[R]]:
        def __wrap_thread_pool_submit(
            call_wrapped: Callable[..., Future[R]],
            instance: futures.ThreadPoolExecutor,
            args: tuple[Callable[..., Any], ...],
            kwargs: dict[str, Any],
        ) -> Future[R]:
            # obtain the original function and wrapped kwargs
            original_func = args[0]
            otel_context = context.get_current()
            attributes = {
                "threadpool.executor": instance._thread_name_prefix,
            }

            def wrapped_func(*func_args: Any, **func_kwargs: Any) -> R:
                token = None
                try:
                    token = context.attach(otel_context)
                    self.queue_count.add(-1, attributes)
                    self.working_items_count.add(1, attributes)
                    return original_func(*func_args, **func_kwargs)
                finally:
                    if token is not None:
                        context.detach(token)

            # replace the original function with the wrapped function
            new_args: tuple[Callable[..., Any], ...] = (wrapped_func,) + args[
                1:
            ]
            self.queue_count.add(1, attributes)

            try:
                future = call_wrapped(*new_args, **kwargs)
            except RuntimeError:
                self.queue_count.add(-1, attributes)
                raise

            self.thread_count.set(len(instance._threads), attributes)
            future.add_done_callback(
                lambda _: self.working_items_count.add(-1, attributes)
            )
            return future

        return __wrap_thread_pool_submit

    def __build_wrap_thread_pool_init(self) -> Callable[..., None]:
        def __wrap_thread_pool_init(
            call_wrapped: Callable[..., None],
            instance: futures.ThreadPoolExecutor,
            args: tuple[Callable[..., Any], ...],
            kwargs: dict[str, Any],
        ) -> None:
            call_wrapped(*args, **kwargs)
            attributes = {
                "threadpool.executor": instance._thread_name_prefix,
            }
            self.max_thread_count.set(instance._max_workers, attributes)

        return __wrap_thread_pool_init
