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
instrument_producer (Callable) - a function with extra user-defined logic to be performed before sending the message
                          this function signature is:
                          def instrument_producer(producer: Producer, tracer_provider=None)
instrument_consumer (Callable) - a function with extra user-defined logic to be performed after consuming a message
                          this function signature is:
                          def instrument_consumer(consumer: Consumer, tracer_provider=None)
for example:
.. code: python
    from opentelemetry.instrumentation.confluentkafka import ConfluentKafkaInstrumentor
    from confluent_kafka import Producer, Consumer

    inst = ConfluentKafkaInstrumentor()

    p = confluent_kafka.Producer({'bootstrap.servers': 'localhost:29092'})
    c = confluent_kafka.Consumer({
        'bootstrap.servers': 'localhost:29092',
        'group.id': 'mygroup',
        'auto.offset.reset': 'earliest'
    })

    # instrument confluent kafka with produce and consume hooks
    p = inst.instrument_producer(p, tracer_provider)
    c = inst.instrument_consumer(c, tracer_provider=tracer_provider)


    # Using kafka as normal now will automatically generate spans,
    # including user custom attributes added from the hooks
    conf = {'bootstrap.servers': "localhost:9092"}
    p.produce('my-topic',b'raw_bytes')
    msg = c.poll()


API
___
"""
from typing import Collection

import confluent_kafka
import wrapt
from confluent_kafka import Producer, Consumer
from opentelemetry import trace, propagate, context
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Tracer, Link, SpanKind
from opentelemetry.instrumentation.utils import unwrap

from kafka_instrumentation.package import _instruments
from kafka_instrumentation.utils import KafkaPropertiesExtractor, _get_span_name, \
    _kafka_setter, _enrich_span, _kafka_getter
from kafka_instrumentation.version import __version__


class AutoInstrumentedProducer(Producer):
    def __init__(self, config):
        super().__init__(config)

    def produce(self, topic, value=None, *args, **kwargs):
        super().produce(topic, value, *args, **kwargs)


class AutoInstrumentedConsumer(Consumer):
    def __init__(self, config):
        super().__init__(config)
        self._current_consume_span = None

    def poll(self, timeout=-1):
        return super().poll(timeout)


class ProxiedProducer(Producer):

    def __init__(self, producer: Producer, tracer: Tracer):
        self._producer = producer
        self._tracer = tracer

    def flush(self, timeout=-1):
        self._producer.flush(timeout)

    def poll(self, timeout=-1):
        self._producer.poll(timeout)

    def produce(self, topic, value=None, *args, **kwargs):
        new_kwargs = kwargs.copy()
        new_kwargs['topic'] = topic
        new_kwargs['value'] = value

        return ConfluentKafkaInstrumentor.wrap_produce(self._producer.produce, self, self._tracer, args, new_kwargs)

    def original_producer(self):
        return self._producer


class ProxiedConsumer(Consumer):

    def __init__(self, consumer: Consumer, tracer: Tracer):
        self._consumer = consumer
        self._tracer = tracer
        self._current_consume_span = None
        self._current_context_token = None

    def committed(self, partitions, timeout=-1):
        return self._consumer.committed(partitions, timeout)

    def consume(self, num_messages=1, *args, **kwargs):
        return self._consumer.consume(num_messages, *args, **kwargs)

    def get_watermark_offsets(self, partition, timeout=-1, *args, **kwargs):
        return self._consumer.get_watermark_offsets(partition, timeout, *args, **kwargs)

    def offsets_for_times(self, partitions, timeout=-1):
        return self._consumer.offsets_for_times(partitions, timeout)

    def poll(self, timeout=-1):
        return ConfluentKafkaInstrumentor.wrap_poll(self._consumer.poll, self, self._tracer, [timeout], {})

    def subscribe(self, topics, on_assign=lambda *args: None, *args, **kwargs):
        self._consumer.subscribe(topics, on_assign, *args, **kwargs)

    def original_consumer(self):
        return self._consumer


class ConfluentKafkaInstrumentor(BaseInstrumentor):
    """An instrumentor for confluent kafka module
    See `BaseInstrumentor`
    """

    @staticmethod
    def instrument_producer(producer: Producer, tracer_provider=None) -> ProxiedProducer:
        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        manual_producer = ProxiedProducer(producer, tracer)

        return manual_producer

    @staticmethod
    def instrument_consumer(consumer: Consumer, tracer_provider=None) -> ProxiedConsumer:
        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        manual_consumer = ProxiedConsumer(consumer, tracer)

        return manual_consumer

    @staticmethod
    def uninstrument_producer(producer) -> Producer:
        if isinstance(producer, ProxiedProducer):
            return producer.original_producer()

    @staticmethod
    def uninstrument_consumer(consumer) -> Consumer:
        if isinstance(consumer, ProxiedConsumer):
            return consumer.original_consumer()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        self._original_kafka_producer = confluent_kafka.Producer
        self._original_kafka_consumer = confluent_kafka.Consumer

        confluent_kafka.Producer = AutoInstrumentedProducer
        confluent_kafka.Consumer = AutoInstrumentedConsumer

        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        self._tracer = tracer

        def _inner_wrap_produce(func, instance, args, kwargs):
            return ConfluentKafkaInstrumentor.wrap_produce(func, instance, self._tracer, args, kwargs)

        def _inner_wrap_poll(func, instance, args, kwargs):
            return ConfluentKafkaInstrumentor.wrap_poll(func, instance, self._tracer, args, kwargs)

        wrapt.wrap_function_wrapper("kafka_instrumentation",
                                    "AutoInstrumentedProducer.produce", _inner_wrap_produce)

        wrapt.wrap_function_wrapper("kafka_instrumentation",
                                    "AutoInstrumentedConsumer.poll", _inner_wrap_poll)

    def _uninstrument(self, **kwargs):
        confluent_kafka.Producer = self._original_kafka_producer
        confluent_kafka.Consumer = self._original_kafka_consumer

        unwrap(AutoInstrumentedProducer, "produce")
        unwrap(AutoInstrumentedConsumer, "poll")

    @staticmethod
    def wrap_produce(func, instance, tracer, args, kwargs):
        topic = kwargs.get("topic")
        if not topic:
            topic = args[0]

        span_name = _get_span_name("send", topic) 
        with tracer.start_as_current_span(name=span_name, kind=trace.SpanKind.PRODUCER) as span:
            headers = KafkaPropertiesExtractor.extract_produce_headers(args, kwargs)
            if headers is None:
                headers = []
                kwargs["headers"] = headers

            topic = KafkaPropertiesExtractor.extract_produce_topic(args)
            bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            _enrich_span(span, topic, bootstrap_servers, operation=MessagingOperationValues.RECEIVE)  # Replace
            propagate.inject(
                headers,
                setter=_kafka_setter,
            )
            return func(*args, **kwargs)
            
    @staticmethod
    def wrap_poll(func, instance, tracer, args, kwargs):
        if instance._current_consume_span:
            context.detach(instance._current_context_token)
            instance._current_context_token = None
            instance._current_consume_span.end()
            instance._current_consume_span = None

        with tracer.start_as_current_span("recv", end_on_exit=True, kind=trace.SpanKind.CONSUMER) as span:
            record = func(*args, **kwargs)
            if record:
                links = []
                ctx = propagate.extract(record.headers(), getter=_kafka_getter)
                if ctx:
                    for item in ctx.values():
                        if hasattr(item, "get_span_context"):
                            links.append(Link(context=item.get_span_context()))

                instance._current_consume_span = tracer.start_span(
                    name=f"{record.topic()} process", links=links, kind=SpanKind.CONSUMER
                )

                bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
                _enrich_span(
                    instance._current_consume_span,
                    record.topic(),
                    bootstrap_servers,
                    record.partition(),
                    record.offset(),
                    operation=MessagingOperationValues.PROCESS,

                )
        instance._current_context_token = context.attach(
            trace.set_span_in_context(instance._current_consume_span))

        return record