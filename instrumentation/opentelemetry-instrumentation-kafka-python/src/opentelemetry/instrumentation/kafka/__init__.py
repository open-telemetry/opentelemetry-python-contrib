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

- **use_message_context_as_parent** (bool) - an optional boolean keyword argument (default: False) to control
  whether the message creation context is used as the parent for the consumer span. When False (the default),
  consumer spans use the ambient context as parent (or create a root span) and link to the message creation
  context. When True, single-record consumer spans use the message creation context as parent and link to any
  active ambient context.

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

API
---
"""

from collections.abc import Collection

import kafka
from wrapt import wrap_function_wrapper

from opentelemetry import trace
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
                ``use_message_context_as_parent``: a bool (default: False) to control consumer span parenting
        """
        tracer_provider = kwargs.get("tracer_provider")
        produce_hook = kwargs.get("produce_hook")
        consume_hook = kwargs.get("consume_hook")
        use_message_context_as_parent = kwargs.get("use_message_context_as_parent", False)

        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        wrap_function_wrapper(kafka.KafkaProducer, "send", _wrap_send(tracer, produce_hook))
        wrap_function_wrapper(
            kafka.KafkaConsumer,
            "__next__",
            _wrap_next(
                tracer,
                consume_hook,
                use_message_context_as_parent=use_message_context_as_parent,
            ),
        )

    def _uninstrument(self, **kwargs):
        unwrap(kafka.KafkaProducer, "send")
        unwrap(kafka.KafkaConsumer, "__next__")
