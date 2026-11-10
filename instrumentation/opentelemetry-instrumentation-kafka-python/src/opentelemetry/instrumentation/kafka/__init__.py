# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrument kafka-python to report instrumentation-kafka produced and consumed messages

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.kafka import KafkaInstrumentor
    from kafka import KafkaProducer, KafkaConsumer

    # Instrument kafka
    KafkaInstrumentor().instrument()

    # report a span of type producer with the default settings
    producer = KafkaProducer(bootstrap_servers=['localhost:9092'])
    producer.send('my-topic', b'raw_bytes')

    def process_msg(message):
        print(message)

    # report a span of type consumer with the default settings
    consumer = KafkaConsumer('my-topic', group_id='my-group', bootstrap_servers=['localhost:9092'])
    for message in consumer:
        # process message
        process_msg(message)

The ``_instrument()`` method accepts the following keyword args:

- **tracer_provider** (TracerProvider) - an optional tracer provider
- **produce_hook** (Callable) - a function with extra user-defined logic to be performed before sending the message

  Function signature:

  .. code:: python

      def produce_hook(span: Span, args, kwargs): ...

- **consume_hook** (Callable) - a function with extra user-defined logic to be performed after consuming a message

  Function signature:

  .. code:: python

      def consume_hook(span: Span, record: kafka.record.ABCRecord, args, kwargs): ...

For example:

.. code:: python

    from opentelemetry.instrumentation.kafka import KafkaInstrumentor
    from kafka import KafkaProducer, KafkaConsumer

    def produce_hook(span, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_produce_hook", "some-value")

    def consume_hook(span, record, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_consume_hook", "some-value")

    # instrument kafka with produce and consume hooks
    KafkaInstrumentor().instrument(produce_hook=produce_hook, consume_hook=consume_hook)

    # Using kafka as normal now will automatically generate spans,
    # including user custom attributes added from the hooks
    producer = KafkaProducer(bootstrap_servers=['localhost:9092'])
    producer.send('my-topic', b'raw_bytes')

    def process_msg(message):
        print(message)

    consumer = KafkaConsumer('my-topic', group_id='my-group', bootstrap_servers=['localhost:9092'])
    for message in consumer:
        # process message
        process_msg(message)

Stable Semantic Conventions
***************************

This instrumentation supports the messaging semantic convention migration plan.
You can control which conventions are emitted by setting the
``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable to one of these values:

- ``messaging`` - emit the stable messaging conventions and stop emitting the
  old experimental conventions.
- ``messaging/dup`` - emit both the old experimental and stable messaging
  conventions during a transition period.

The environment variable accepts a comma-separated list of opt-in values. For
example, ``messaging,http/dup`` enables stable messaging conventions and emits
both old and stable HTTP conventions.

By default, when the environment variable is not set, the old experimental
messaging conventions are emitted.

The old and stable attributes correspond as follows:

============================= ======================================
old                           stable
============================= ======================================
``messaging.destination``     ``messaging.destination.name``
``messaging.kafka.partition`` ``messaging.destination.partition.id``
``messaging.url``             ``server.address`` and ``server.port``
============================= ======================================

``messaging.destination.partition.id`` is a string, while
``messaging.kafka.partition`` was an integer.

``messaging.url`` carries the whole ``bootstrap_servers`` value JSON-encoded.
``server.address`` and ``server.port`` carry the host and the port of its
first entry instead, parsed out of it, because the stable conventions define
them as one host and one port rather than as a connection string.
``server.port`` is omitted when that entry names no port.

The stable conventions also add ``messaging.operation.name`` and
``messaging.operation.type``, which the old conventions did not have.
``messaging.system`` is emitted in every mode.

API
---
"""

from collections.abc import Collection

import kafka
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _get_semconv_opt_in_modes,
    _OpenTelemetryStabilitySignalType,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.kafka.package import _instruments
from opentelemetry.instrumentation.kafka.utils import _wrap_next, _wrap_send
from opentelemetry.instrumentation.kafka.version import __version__
from opentelemetry.instrumentation.utils import unwrap


class KafkaInstrumentor(BaseInstrumentor):
    """An instrumentor for kafka module
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments the kafka module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``produce_hook``: a callable to be executed just before producing a message
                ``consume_hook``: a callable to be executed just after consuming a message
        """
        tracer_provider = kwargs.get("tracer_provider")
        produce_hook = kwargs.get("produce_hook")
        consume_hook = kwargs.get("consume_hook")

        sem_conv_opt_in_mode = _get_semconv_opt_in_modes((_OpenTelemetryStabilitySignalType.MESSAGING,))[
            _OpenTelemetryStabilitySignalType.MESSAGING
        ]

        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url=_get_schema_url_for_signal_types([_OpenTelemetryStabilitySignalType.MESSAGING]),
        )

        wrap_function_wrapper(
            kafka.KafkaProducer,
            "send",
            _wrap_send(tracer, produce_hook, sem_conv_opt_in_mode),
        )
        wrap_function_wrapper(
            kafka.KafkaConsumer,
            "__next__",
            _wrap_next(tracer, consume_hook, sem_conv_opt_in_mode),
        )

    def _uninstrument(self, **kwargs):
        unwrap(kafka.KafkaProducer, "send")
        unwrap(kafka.KafkaConsumer, "__next__")
