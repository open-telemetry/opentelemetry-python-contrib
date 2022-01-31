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
Instrument `confluent-kafka-python` to report instrumentation-confluent-kafka produced and consumed messages

Usage
-----

..code:: python

    from opentelemetry.instrumentation.confluentkafka import ConfluentKafkaInstrumentor
    from confluent_kafka import Producer, Consumer

    # Instrument kafka
    ConfluentKafkaInstrumentor().instrument()

    # report a span of type producer with the default settings
    conf1 = {'bootstrap.servers': "localhost:9092"}
    producer = Producer(conf1)
    producer.produce('my-topic',b'raw_bytes')

    conf2 = {'bootstrap.servers': "localhost:9092",
        'group.id': "foo",
        'auto.offset.reset': 'smallest'}
    # report a span of type consumer with the default settings
    consumer = Consumer(conf2)
    def basic_consume_loop(consumer, topics):
        try:
            consumer.subscribe(topics)
            running = True
            while running:
                msg = consumer.poll(timeout=1.0)
                if msg is None: continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition event
                        sys.stderr.write('%% %s [%d] reached end at offset %d\n' %
                                         (msg.topic(), msg.partition(), msg.offset()))
                    elif msg.error():
                        raise KafkaException(msg.error())
                else:
                    msg_process(msg)
        finally:
            # Close down consumer to commit final offsets.
            consumer.close()

    basic_consume_loop(consumer, "my-topic")


The `_instrument` method accepts the following keyword args:
tracer_provider (TracerProvider) - an optional tracer provider
produce_hook (Callable) - a function with extra user-defined logic to be performed before sending the message
                          this function signature is:
                          def produce_hook(span: Span, args, kwargs)
consume_hook (Callable) - a function with extra user-defined logic to be performed after consuming a message
                          this function signature is:
                          def consume
                          _hook(span: Span, record: Message, args, kwargs)
for example:
.. code: python
    from opentelemetry.instrumentation.confluentkafka import ConfluentKafkaInstrumentor
     from confluent_kafka import Producer, Consumer

    def produce_hook(span, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_produce_hook", "some-value")
    def consume_hook(span, record, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_consume_hook", "some-value")

    # instrument confluent kafka with produce and consume hooks
    ConfluentKafkaInstrumentor().instrument(produce_hook=produce_hook, consume_hook=consume_hook)

    # Using kafka as normal now will automatically generate spans,
    # including user custom attributes added from the hooks
    conf = {'bootstrap.servers': "localhost:9092"}
    producer = Producer(conf)
    producer.produce('my-topic',b'raw_bytes')

API
___
"""
from typing import Collection

from confluent_kafka import Producer, Consumer

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.confluentkafka.package import _instruments
from opentelemetry.instrumentation.confluentkafka.utils import _wrap_produce, _wrap_poll
from opentelemetry.instrumentation.confluentkafka.version import __version__

from forbiddenfruit import curse


class ConfluentKafkaInstrumentor(BaseInstrumentor):
    """An instrumentor for confluent kafka module
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments the confluent kafka module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``produce_hook``: a callable to be executed just before producing a message
                ``consume_hook``: a callable to be executed just after consuming a message
        """
        tracer_provider = kwargs.get("tracer_provider")
        produce_hook = kwargs.get("produce_hook")
        consume_hook = kwargs.get("consume_hook")

        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        curse(Producer, "trace_produce", _wrap_produce(tracer, produce_hook))
        curse(Consumer, "trace_poll", _wrap_poll(tracer, consume_hook))

    def _uninstrument(self, **kwargs):
        reverse(Producer, "trace_produce")
        reverse(Consumer, "trace_poll")
