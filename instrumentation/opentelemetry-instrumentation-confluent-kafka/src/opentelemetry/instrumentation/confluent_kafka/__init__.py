# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrument confluent-kafka-python to report instrumentation-confluent-kafka produced and consumed messages

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
    from confluent_kafka import Producer, Consumer

    # Instrument kafka
    ConfluentKafkaInstrumentor().instrument()

    # report a span of type producer with the default settings
    conf1 = {'bootstrap.servers': "localhost:9092"}
    producer = Producer(conf1)
    producer.produce('my-topic',b'raw_bytes')
    conf2 = {'bootstrap.servers': "localhost:9092", 'group.id': "foo", 'auto.offset.reset': 'smallest'}
    # report a span of type consumer with the default settings
    consumer = Consumer(conf2)

    def msg_process(msg):
        print(msg)

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
                        sys.stderr.write(f"{msg.topic()} [{msg.partition()}] reached end at offset {msg.offset()}")
                    elif msg.error():
                        raise KafkaException(msg.error())
                else:
                    msg_process(msg)
        finally:
            # Close down consumer to commit final offsets.
            consumer.close()

    basic_consume_loop(consumer, ["my-topic"])

The _instrument method accepts the following keyword args:
  tracer_provider (TracerProvider) - an optional tracer provider

  instrument_producer (Callable) - a function with extra user-defined logic to be performed before sending the message
    this function signature is:

  def instrument_producer(producer: Producer, tracer_provider=None)

    instrument_consumer (Callable) - a function with extra user-defined logic to be performed after consuming a message
        this function signature is:

  def instrument_consumer(consumer: Consumer, tracer_provider=None)
    for example:

.. code:: python

    from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
    from opentelemetry.trace import get_tracer_provider

    from confluent_kafka import Producer, Consumer

    inst = ConfluentKafkaInstrumentor()
    tracer_provider = get_tracer_provider()

    p = Producer({'bootstrap.servers': 'localhost:9092'})
    c = Consumer({
        'bootstrap.servers': 'localhost:9092',
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

"""

from typing import Collection

import confluent_kafka
import wrapt
from confluent_kafka import Consumer, Producer

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MessagingOperationTypeValues,
)
from opentelemetry.trace import Tracer

from .package import _instruments
from .utils import (
    KafkaPropertiesExtractor,
    _create_new_consume_span,
    _end_current_consume_span,
    _enrich_span,
    _get_span_name,
    _kafka_setter,
)
from .version import __version__


def _capture_config(args, kwargs):
    """Return the config dict that was passed to a Producer/Consumer
    constructor, regardless of whether it was supplied positionally, as
    ``conf=`` kwarg, or (for Consumer) expanded as **kwargs."""
    if args and isinstance(args[0], dict):
        return args[0]
    conf = kwargs.get("conf")
    if isinstance(conf, dict):
        return conf
    # confluent_kafka.Consumer also supports Consumer(**conf) — in that case
    # the kwargs themselves are the config.
    if kwargs:
        return dict(kwargs)
    return None


class AutoInstrumentedProducer(Producer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = _capture_config(args, kwargs)

    # This method is deliberately implemented in order to allow wrapt to wrap this function
    def produce(self, topic, value=None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg,useless-super-delegation
        super().produce(topic, value, *args, **kwargs)


class AutoInstrumentedConsumer(Consumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = _capture_config(args, kwargs)
        self._current_consume_span = None

    # This method is deliberately implemented in order to allow wrapt to wrap this function
    def poll(self, timeout=-1):  # pylint: disable=useless-super-delegation
        return super().poll(timeout)

    # This method is deliberately implemented in order to allow wrapt to wrap this function
    def consume(self, *args, **kwargs):  # pylint: disable=useless-super-delegation
        return super().consume(*args, **kwargs)

    # This method is deliberately implemented in order to allow wrapt to wrap this function
    def close(self):  # pylint: disable=useless-super-delegation
        return super().close()


class ProxiedProducer(Producer):
    def __init__(self, producer: Producer, tracer: Tracer):
        self._producer = producer
        self._tracer = tracer
        # Surface the wrapped producer's config (if any) so that
        # KafkaPropertiesExtractor.extract_bootstrap_servers can read it
        # through this proxy.
        self.config = getattr(producer, "config", None)

    def flush(self, timeout=-1):
        return self._producer.flush(timeout)

    def poll(self, timeout=-1):
        return self._producer.poll(timeout)

    def purge(self, in_queue=True, in_flight=True, blocking=True):
        self._producer.purge(in_queue, in_flight, blocking)

    def produce(self, topic, value=None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        new_kwargs = kwargs.copy()
        new_kwargs["topic"] = topic
        new_kwargs["value"] = value

        return ConfluentKafkaInstrumentor.wrap_produce(
            self._producer.produce, self, self._tracer, args, new_kwargs
        )

    def original_producer(self):
        return self._producer


class ProxiedConsumer(Consumer):
    def __init__(self, consumer: Consumer, tracer: Tracer):
        self._consumer = consumer
        self._tracer = tracer
        self._current_consume_span = None
        self._current_context_token = None
        # See ProxiedProducer.__init__ for rationale.
        self.config = getattr(consumer, "config", None)

    def close(self, *args, **kwargs):
        return ConfluentKafkaInstrumentor.wrap_close(
            self._consumer.close, self, args, kwargs
        )

    def committed(self, partitions, timeout=-1):
        return self._consumer.committed(partitions, timeout)

    def commit(self, *args, **kwargs):
        return self._consumer.commit(*args, **kwargs)

    def consume(self, *args, **kwargs):
        return ConfluentKafkaInstrumentor.wrap_consume(
            self._consumer.consume,
            self,
            self._tracer,
            args,
            kwargs,
        )

    def get_watermark_offsets(self, partition, timeout=-1, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        return self._consumer.get_watermark_offsets(
            partition, timeout, *args, **kwargs
        )

    def offsets_for_times(self, partitions, timeout=-1):
        return self._consumer.offsets_for_times(partitions, timeout)

    def poll(self, timeout=-1):
        return ConfluentKafkaInstrumentor.wrap_poll(
            self._consumer.poll, self, self._tracer, [timeout], {}
        )

    def subscribe(self, topics, on_assign=lambda *args: None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        self._consumer.subscribe(topics, on_assign, *args, **kwargs)

    def original_consumer(self):
        return self._consumer


class ConfluentKafkaInstrumentor(BaseInstrumentor):
    """An instrumentor for confluent kafka module
    See `BaseInstrumentor`
    """

    @staticmethod
    def instrument_producer(
        producer: Producer, tracer_provider=None
    ) -> ProxiedProducer:
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        manual_producer = ProxiedProducer(producer, tracer)

        return manual_producer

    @staticmethod
    def instrument_consumer(
        consumer: Consumer, tracer_provider=None
    ) -> ProxiedConsumer:
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        manual_consumer = ProxiedConsumer(consumer, tracer)

        return manual_consumer

    @staticmethod
    def uninstrument_producer(producer: Producer) -> Producer:
        if isinstance(producer, ProxiedProducer):
            return producer.original_producer()
        return producer

    @staticmethod
    def uninstrument_consumer(consumer: Consumer) -> Consumer:
        if isinstance(consumer, ProxiedConsumer):
            return consumer.original_consumer()
        return consumer

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        # TODO: should probably wrap methods directly instead of going through
        # these classes. Hopefully it'll make the patching work if called after
        # the original classes have already been imported,  #4270
        self._original_kafka_producer = confluent_kafka.Producer
        self._original_kafka_consumer = confluent_kafka.Consumer

        confluent_kafka.Producer = AutoInstrumentedProducer
        confluent_kafka.Consumer = AutoInstrumentedConsumer

        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        self._tracer = tracer

        def _inner_wrap_produce(func, instance, args, kwargs):
            return ConfluentKafkaInstrumentor.wrap_produce(
                func, instance, self._tracer, args, kwargs
            )

        def _inner_wrap_poll(func, instance, args, kwargs):
            return ConfluentKafkaInstrumentor.wrap_poll(
                func, instance, self._tracer, args, kwargs
            )

        def _inner_wrap_consume(func, instance, args, kwargs):
            return ConfluentKafkaInstrumentor.wrap_consume(
                func, instance, self._tracer, args, kwargs
            )

        def _inner_wrap_close(func, instance, args, kwargs):
            return ConfluentKafkaInstrumentor.wrap_close(
                func, instance, args, kwargs
            )

        wrapt.wrap_function_wrapper(
            AutoInstrumentedProducer,
            "produce",
            _inner_wrap_produce,
        )

        wrapt.wrap_function_wrapper(
            AutoInstrumentedConsumer,
            "poll",
            _inner_wrap_poll,
        )

        wrapt.wrap_function_wrapper(
            AutoInstrumentedConsumer,
            "consume",
            _inner_wrap_consume,
        )

        wrapt.wrap_function_wrapper(
            AutoInstrumentedConsumer,
            "close",
            _inner_wrap_close,
        )

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
        with tracer.start_as_current_span(
            name=span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            headers = KafkaPropertiesExtractor.extract_produce_headers(
                args, kwargs
            )
            if headers is None:
                headers = []
                kwargs["headers"] = headers

            topic = KafkaPropertiesExtractor.extract_produce_topic(
                args, kwargs
            )
            bootstrap_servers = (
                KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            )
            _enrich_span(
                span,
                topic,
                operation=MessagingOperationTypeValues.PUBLISH,
                bootstrap_servers=bootstrap_servers,
            )  # Publish
            propagate.inject(
                headers,
                setter=_kafka_setter,
            )
            return func(*args, **kwargs)

    @staticmethod
    def wrap_poll(func, instance, tracer, args, kwargs):
        if instance._current_consume_span:
            _end_current_consume_span(instance)

        record = func(*args, **kwargs)
        if record:
            bootstrap_servers = (
                KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            )
            with tracer.start_as_current_span(
                "recv", end_on_exit=True, kind=trace.SpanKind.CONSUMER
            ):
                _create_new_consume_span(instance, tracer, [record])
                _enrich_span(
                    instance._current_consume_span,
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    operation=MessagingOperationTypeValues.PROCESS,
                    bootstrap_servers=bootstrap_servers,
                )
            instance._current_context_token = context.attach(
                trace.set_span_in_context(instance._current_consume_span)
            )

        return record

    @staticmethod
    def wrap_consume(func, instance, tracer, args, kwargs):
        if instance._current_consume_span:
            _end_current_consume_span(instance)

        records = func(*args, **kwargs)
        if len(records) > 0:
            bootstrap_servers = (
                KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            )
            with tracer.start_as_current_span(
                "recv", end_on_exit=True, kind=trace.SpanKind.CONSUMER
            ):
                _create_new_consume_span(instance, tracer, records)
                _enrich_span(
                    instance._current_consume_span,
                    records[0].topic(),
                    operation=MessagingOperationTypeValues.PROCESS,
                    bootstrap_servers=bootstrap_servers,
                )
            instance._current_context_token = context.attach(
                trace.set_span_in_context(instance._current_consume_span)
            )

        return records

    @staticmethod
    def wrap_close(func, instance, args, kwargs):
        if instance._current_consume_span:
            _end_current_consume_span(instance)
        func(*args, **kwargs)
