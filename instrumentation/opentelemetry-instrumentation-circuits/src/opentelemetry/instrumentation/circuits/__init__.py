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

Usage
-----

The OpenTelemetry ``circuits`` integration traces circuits event manager

Usage
-----

.. code-block:: python

    from circuits import Component, Event
    from opentelemetry.instrumentation.circuits import CircuitsInstrumentor


    CircuitsInstrumentor().instrument()

    class hello(Event):
        #hello Event


    class App(Component):
        def hello(self):
            print("Hello World!")
        def started(self, component):
            self.fire(hello())
            self.stop()

    App().run()
            
API
---
"""
# pylint: disable=no-value-for-parameter

import logging
from typing import Collection

import circuits
from circuits.core import Manager
from wrapt import wrap_function_wrapper as _wrap

from opentelemetry.instrumentation.circuits.package import _instruments
from opentelemetry.instrumentation.circuits.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import Meter, get_meter
from opentelemetry.trace import SpanKind, Tracer, get_tracer

logger = logging.getLogger(__name__)


def _with_tracer_wrapper(func):
    """Helper for providing tracer for wrapper functions."""

    def _with_meter_and_tracer(meter: Meter, tracer: Tracer):
        def wrapper(wrapped, instance, args, kwargs):
            return func(meter, tracer, wrapped, instance, args, kwargs)

        return wrapper

    return _with_meter_and_tracer


@_with_tracer_wrapper
def _wrap_tick(meter: Meter, tracer: Tracer, wrapped, instance, args, kwargs):
    """Wrap `Manager.tick()`"""
    with tracer.start_as_current_span(
        "circuits.Manager.tick",
        kind=SpanKind.INTERNAL,
    ) as span:
        return wrapped(*args, **kwargs)


@_with_tracer_wrapper
def _wrap_processtask(meter: Meter, tracer: Tracer, wrapped, instance, args, kwargs):
    """Wrap `Manager.processTask()`"""
    with tracer.start_as_current_span(
        "circuits.Manager.processTask",
        kind=SpanKind.INTERNAL,
    ) as span:
        if span.is_recording() and args and len(args) >= 2:
            event, task, *_ = args
            span.set_attributes(
                {
                    "circuits.event_name": event.name,
                    "circuits.event_module": event.__module__,
                    "circuits.task_name": task.__qualname__,
                }
            )
        return wrapped(*args, **kwargs)


@_with_tracer_wrapper
def _wrap_handler(meter: Meter, tracer: Tracer, wrapped, instance, args, kwargs):
    with tracer.start_as_current_span(
        "circuits.core.handler", kind=SpanKind.SERVER
    ) as span:
        if span.is_recording() and args and not isinstance(args[0], bool):
            span.set_attribute("circuits.handler.name", args[0])
        return wrapped(*args, **kwargs)


class CircuitsInstrumentor(BaseInstrumentor):
    """An instrumentor for circuits

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        meter = get_meter(__name__, __version__, kwargs.get("meter_provider"))
        tracer = get_tracer(__name__, __version__, kwargs.get("tracer_provider"))

        _wrap(Manager, "tick", _wrap_tick(meter, tracer))
        _wrap(Manager, "processTask", _wrap_processtask(meter, tracer))
        _wrap(circuits.core, "handler", _wrap_handler(meter, tracer))

    def _uninstrument(self, **kwargs):
        unwrap(circuits.core, "handler")
        unwrap(Manager, "processTask")
        unwrap(Manager, "tick")
