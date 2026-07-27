# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrument `faust-streaming`_ to trace messages sent to Kafka and events
processed by faust agents.

.. _faust-streaming: https://pypi.org/project/faust-streaming/

The instrumentation relies on faust's built-in sensor API: every
``faust.App`` created after calling ``instrument()`` gets an
:class:`~opentelemetry.instrumentation.faust.OpenTelemetrySensor`
added to it.  The sensor:

* starts a ``PRODUCER`` span for every message sent to a Kafka topic
  (``Topic.send()``, ``App.send()``, agent replies, and so on) and injects
  the span context into the Kafka message headers,
* starts a ``CONSUMER`` span around every event processed by a stream
  (for example the body of a faust agent), using the context extracted
  from the incoming Kafka message headers as parent.

Applications created *before* calling ``instrument()`` are not
instrumented automatically; use ``FaustInstrumentor().instrument_app(app)``
to instrument them explicitly.

Usage
-----

.. code:: python

    import faust
    from opentelemetry.instrumentation.faust import FaustInstrumentor

    # Instrument faust before creating the app
    FaustInstrumentor().instrument()

    app = faust.App("example", broker="kafka://localhost:9092")
    orders_topic = app.topic("orders")

    @app.agent(orders_topic)
    async def process_orders(orders):
        async for order in orders:
            ...  # each event is processed inside a consumer span

    async def send_order():
        # produces a producer span and propagates its context via headers
        await orders_topic.send(value=b"order payload")

The ``instrument()`` method accepts the following keyword args:

- **tracer_provider** (TracerProvider) - an optional tracer provider

- **produce_hook** (Callable) - a function with extra user-defined logic
  to be performed before sending a message

  Function signature:

  .. code:: python

      def produce_hook(span: Span, message: faust.types.tuples.PendingMessage): ...

- **process_hook** (Callable) - a function with extra user-defined logic
  to be performed when a stream starts processing an event

  Function signature:

  .. code:: python

      def process_hook(span: Span, event: faust.types.EventT): ...

For example:

.. code:: python

    import faust
    from opentelemetry.instrumentation.faust import FaustInstrumentor

    def produce_hook(span, message):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_produce_hook", "some-value")

    def process_hook(span, event):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_process_hook", "some-value")

    # instrument faust with produce and process hooks
    FaustInstrumentor().instrument(produce_hook=produce_hook, process_hook=process_hook)

API
---
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Collection
from weakref import WeakKeyDictionary

import faust
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.faust.package import _instruments
from opentelemetry.instrumentation.faust.sensor import OpenTelemetrySensor
from opentelemetry.instrumentation.faust.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

if TYPE_CHECKING:
    from typing import TypedDict

    from typing_extensions import Unpack

    from .sensor import ProcessHookT, ProduceHookT

    class InstrumentKwargs(TypedDict, total=False):
        tracer_provider: trace.TracerProvider
        produce_hook: ProduceHookT
        process_hook: ProcessHookT

    class UninstrumentKwargs(TypedDict, total=False):
        pass


__all__ = ["FaustInstrumentor", "OpenTelemetrySensor"]

_instrumented_apps: WeakKeyDictionary[faust.App, OpenTelemetrySensor] = (
    WeakKeyDictionary()
)


def _add_sensor(
    app: faust.App,
    tracer: trace.Tracer,
    produce_hook: ProduceHookT = None,
    process_hook: ProcessHookT = None,
) -> None:
    if app in _instrumented_apps:
        return
    sensor = OpenTelemetrySensor(tracer, produce_hook, process_hook)
    app.sensors.add(sensor)
    _instrumented_apps[app] = sensor


def _remove_sensor(app: faust.App) -> None:
    sensor = _instrumented_apps.pop(app, None)
    if sensor is None:
        return
    try:
        app.sensors.remove(sensor)
    except KeyError:
        pass


def _wrap_app_init(
    tracer: trace.Tracer,
    produce_hook: ProduceHookT,
    process_hook: ProcessHookT,
) -> Callable[..., None]:
    def _traced_init(
        func: Callable[..., None],
        instance: faust.App,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        func(*args, **kwargs)
        _add_sensor(instance, tracer, produce_hook, process_hook)

    return _traced_init


class FaustInstrumentor(BaseInstrumentor):
    """An instrumentor for faust-streaming
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Unpack[InstrumentKwargs]) -> None:
        """Instruments the faust module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``produce_hook``: a callable to be executed just before
                    a message is sent to Kafka.
                ``process_hook``: a callable to be executed when a stream
                    starts processing an event.
        """
        tracer_provider = kwargs.get("tracer_provider")

        produce_hook = kwargs.get("produce_hook")
        if not callable(produce_hook):
            produce_hook = None

        process_hook = kwargs.get("process_hook")
        if not callable(process_hook):
            process_hook = None

        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url=Schemas.V1_27_0.value,
        )

        wrap_function_wrapper(
            faust.App,
            "__init__",
            _wrap_app_init(tracer, produce_hook, process_hook),
        )

    def _uninstrument(self, **kwargs: Unpack[UninstrumentKwargs]) -> None:
        unwrap(faust.App, "__init__")
        for app in list(_instrumented_apps):
            _remove_sensor(app)

    @staticmethod
    def instrument_app(
        app: faust.App,
        tracer_provider: trace.TracerProvider | None = None,
        produce_hook: ProduceHookT = None,
        process_hook: ProcessHookT = None,
    ) -> None:
        """Instrument an existing ``faust.App`` instance."""
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url=Schemas.V1_27_0.value,
        )
        _add_sensor(app, tracer, produce_hook, process_hook)

    @staticmethod
    def uninstrument_app(app: faust.App) -> None:
        """Remove instrumentation from a ``faust.App`` instance."""
        _remove_sensor(app)
