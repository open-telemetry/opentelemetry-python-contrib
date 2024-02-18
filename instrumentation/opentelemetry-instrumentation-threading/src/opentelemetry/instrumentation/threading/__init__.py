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
the OpenTelemetry context is propagated across threads.

When instrumented, new threads created using `threading.Thread` or `threading.Timer`
will have the current OpenTelemetry context attached, and this context will be
re-activated in the thread's run method.
"""

import threading
from typing import Collection
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.threading.package import _instruments
from opentelemetry.instrumentation.threading.version import __version__
from opentelemetry import context, trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from wrapt import wrap_function_wrapper


class ThreadingInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        self._instrument_thread()
        self._instrument_timer()

    def _uninstrument(self, **kwargs):
        self._uninstrument_thread()
        self._uninstrument_timer()

    @staticmethod
    def _instrument_thread():
        wrap_function_wrapper(threading.Thread, 'start',
                              ThreadingInstrumentor.__wrap_threading_start)
        wrap_function_wrapper(threading.Thread, 'run',
                              ThreadingInstrumentor.__wrap_threading_run)

    @staticmethod
    def _instrument_timer():
        wrap_function_wrapper(threading.Timer, 'start',
                              ThreadingInstrumentor.__wrap_threading_start)
        wrap_function_wrapper(threading.Timer, 'run',
                              ThreadingInstrumentor.__wrap_threading_run)

    @staticmethod
    def _uninstrument_thread():
        unwrap(threading.Thread, "start")
        unwrap(threading.Thread, "run")

    @staticmethod
    def _uninstrument_timer():
        unwrap(threading.Timer, "start")
        unwrap(threading.Timer, "run")

    @staticmethod
    def __wrap_threading_start(call_wrapped, instance, args, kwargs):
        span = trace.get_current_span()
        instance._otel_context = trace.set_span_in_context(span)
        return call_wrapped(*args, **kwargs)

    @staticmethod
    def __wrap_threading_run(call_wrapped, instance, args, kwargs):
        token = None
        try:
            token = context.attach(instance._otel_context)
            return call_wrapped(*args, **kwargs)
        finally:
            context.detach(token)
