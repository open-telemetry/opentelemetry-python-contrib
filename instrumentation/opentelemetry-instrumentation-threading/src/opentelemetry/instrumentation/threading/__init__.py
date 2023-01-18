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

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

#from opentelemetry.instrumentation.threading.package import _instruments
from opentelemetry.instrumentation.threading.version import __version__

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

class ThreadingInstrumentor(BaseInstrumentor):  # pylint: disable=empty-docstring
    
    # def instrumentation_dependencies(self) -> Collection[str]:
    #     return _instruments

    def _instrument(self, **kwargs):

        tracer_provider = kwargs.get("tracer_provider", None) or get_tracer_provider()
        tracer = get_tracer(__name__, __version__, tracer_provider)
        start_func = getattr(threading.Thread, "start")
        setattr(
            threading.Thread, start_func.__name__, wrap_threading_start(start_func, tracer)
        )

def wrap_threading_start(start_func, tracer):
    """Wrap the start function from thread. Put the tracer information in the 
    threading object.
    """
 
    def call(self):
        with tracer.start_as_current_span(
            "thread.start",
            kind=SpanKind.INTERNAL,
        ) as span:
                if span.is_recording():
                    thread_name = start_func.__name__ or DEFAULT_THREAD_NAME
                    span.setr_attribute(ATTRIBUTE_THREAD_NAME, thread_name)
            
        return start_func(self)
        
    return call
