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

# pylint: disable=empty-docstring,no-value-for-parameter,no-member,no-name-in-module

import threading # pylint: disable=import-self
from os import environ
from typing import Collection
from opentelemetry import context
from wrapt import wrap_function_wrapper as _wrap
from opentelemetry.instrumentation.utils import unwrap

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

from opentelemetry.instrumentation.threading.package import _instruments
from opentelemetry.instrumentation.threading.version import __version__

from opentelemetry import trace
from opentelemetry.trace import (
    INVALID_SPAN,
    INVALID_SPAN_CONTEXT,
    get_current_span,
    get_tracer_provider,
    get_tracer,
    SpanKind
)

ATTRIBUTE_THREAD_NAME = "currentthread.name"
DEFAULT_THREAD_NAME = "thread"
ATTRIBUTE_TARGET_NAME = "currenttarget.name"
DEFAULT_TARGET_NAME = "None"

def _with_tracer_wrapper(func):
    """Helper for providing tracer for wrapper functions."""

    def _with_tracer(tracer):
        def wrapper(wrapped, instance, args, kwargs):
            return func(tracer, wrapped, instance, args, kwargs)

        return wrapper

    return _with_tracer

def _wrap_target(ctx, target_func, tracer):
    """Helper for providing tracer for wrapper functions."""
    context.attach(ctx)
    with tracer.start_as_current_span(
        "threading.Thread.target",
        kind=SpanKind.INTERNAL,
    ) as span:
        if span.is_recording():
            span.set_attribute(ATTRIBUTE_TARGET_NAME, target_func.__name__)
    return target_func

@_with_tracer_wrapper
def _wrap_thread(tracer, wrapped, instance, args, kwargs):
    """Wrap `Threading.thread`"""

    target_func = kwargs.get("target")
    
    with tracer.start_as_current_span(
        "threading.Thread",
        kind=SpanKind.INTERNAL,
    ) as span:
        if span.is_recording():
            ctx = context.get_current()
            kwargs["target"] = _wrap_target(ctx, target_func, tracer)
            span.set_attribute(ATTRIBUTE_THREAD_NAME, wrapped.__name__)
        return wrapped(*args, **kwargs)

class _InstrumentedThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_span = None

    def start(self):
        self._parent_span = get_current_span()
        super().start()

    def run(self):
        parent_span = self._parent_span or get_current_span()
        trace.set_span_in_context(parent_span)
        super().run()

class ThreadingInstrumentor(BaseInstrumentor):  # pylint: disable=empty-docstring
    
    original_threadcls = threading.Thread

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments


    def _instrument(self, *args,  **kwargs):

        tracer_provider = kwargs.get("tracer_provider", None) or get_tracer_provider()

        tracer = get_tracer(__name__, __version__, tracer_provider)
        threading.Thread = _InstrumentedThread
        _InstrumentedThread._tracer = tracer
        
    def _uninstrument(self, **kwargs):
        threading.Thread = self.original_threadcls        