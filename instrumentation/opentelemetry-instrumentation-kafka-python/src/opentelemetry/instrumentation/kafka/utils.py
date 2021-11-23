import json
from logging import getLogger
from typing import Callable, Dict, List, Optional

from kafka import KafkaConsumer

from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.context.context import Context
from opentelemetry.propagate import extract, inject
from opentelemetry.propagators import textmap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer, set_span_in_context
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


class KafkaInstrumentorContextManager:
    def __init__(self):
        self.spans = dict()
        self.tokens = dict()

    def set_consumer_context(
        self, consumer: KafkaConsumer, context: Context, span: Span
    ):
        self.set_span(consumer, span)
        self.attach_context(consumer, context)

    def set_span(self, consumer: KafkaConsumer, span: Span):
        self.close_span(consumer)
        self.spans[consumer] = span

    def close_span(self, consumer: KafkaConsumer):
        if consumer in self.spans:
            self.spans.get(consumer).close()
            del self.spans[consumer]

    def attach_context(self, consumer: KafkaConsumer, context: Context):
        self.detach_context(consumer)
        self.tokens[consumer] = attach(context)

    def detach_context(self, consumer: KafkaConsumer):
        if consumer in self.tokens:
            detach(self.tokens.get(consumer))
            del self.tokens[consumer]

    def close(self, kafka_consumer: KafkaConsumer = None):
        if kafka_consumer:
            self.close_span(kafka_consumer)
            self.detach_context(kafka_consumer)
        else:
            for consumer in self.spans:
                self.close_span(consumer)
            for consumer in self.tokens:
                self.detach_context(consumer)


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        return instance.config.get("bootstrap_servers")

    @staticmethod
    def _extract_argument(key, position, default_value, args, kwargs):
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_send_topic(args):
        """extract topic from `send` method arguments in KafkaProducer class"""
        if len(args) > 0:
            return args[0]
        return "unknown"

    @staticmethod
    def extract_send_value(args, kwargs):
        """extract value from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "value", 1, None, args, kwargs
        )

    @staticmethod
    def extract_send_key(args, kwargs):
        """extract key from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "key", 2, None, args, kwargs
        )

    @staticmethod
    def extract_send_headers(args, kwargs):
        """extract headers from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "headers", 3, None, args, kwargs
        )

    @staticmethod
    def extract_send_partition(instance, args, kwargs):
        """extract partition `send` method arguments, using the `_partition` method in KafkaProducer class"""
        topic = KafkaPropertiesExtractor.extract_send_topic(args)
        key = KafkaPropertiesExtractor.extract_send_key(args, kwargs)
        value = KafkaPropertiesExtractor.extract_send_value(args, kwargs)
        partition = KafkaPropertiesExtractor._extract_argument(
            "partition", 4, None, args, kwargs
        )
        key_bytes = instance._serialize(
            instance.config["key_serializer"], topic, key
        )
        value_bytes = instance._serialize(
            instance.config["value_serializer"], topic, value
        )
        valid_types = (bytes, bytearray, memoryview, type(None))
        if (
            type(key_bytes) not in valid_types
            or type(value_bytes) not in valid_types
        ):
            return None
        return instance._partition(
            topic, partition, key, value, key_bytes, value_bytes
        )


HookT = Callable[[Span, List, Dict], None]


def dummy_callback(span, args, kwargs):
    ...


class KafkaContextGetter(textmap.Getter):
    def get(self, carrier: textmap.CarrierT, key: str) -> Optional[List[str]]:
        if carrier is None:
            return None

        for item_key, value in carrier:
            if item_key == key:
                if value is not None:
                    return [value.decode()]
        return None

    def keys(self, carrier: textmap.CarrierT) -> List[str]:
        if carrier is None:
            return []
        return [key for (key, value) in carrier]


class KafkaContextSetter(textmap.Setter):
    def set(self, carrier: textmap.CarrierT, key: str, value: str) -> None:
        if carrier is None or key is None:
            return

        if value:
            value = value.encode()
        carrier.append((key, value))


_kafka_getter = KafkaContextGetter()
_kafka_setter = KafkaContextSetter()


def _enrich_span(
    span, bootstrap_servers: List[str], topic: str, partition: int
):
    if span.is_recording():
        span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "kafka")
        span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)
        span.set_attribute(SpanAttributes.MESSAGING_KAFKA_PARTITION, partition)
        span.set_attribute(
            SpanAttributes.MESSAGING_URL, json.dumps(bootstrap_servers)
        )


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"


def _wrap_send(tracer: Tracer, produce_hook: HookT) -> Callable:
    def _traced_send(func, instance, args, kwargs):
        headers = KafkaPropertiesExtractor.extract_send_headers(args, kwargs)
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = KafkaPropertiesExtractor.extract_send_topic(args)
        bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(
            instance
        )
        partition = KafkaPropertiesExtractor.extract_send_partition(
            instance, args, kwargs
        )
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            _enrich_span(span, bootstrap_servers, topic, partition)
            inject(
                headers,
                context=set_span_in_context(span),
                setter=_kafka_setter,
            )
            try:
                produce_hook(span, args, kwargs)
            except Exception as hook_exception:  # pylint: disable=W0703
                _LOG.exception(hook_exception)

        return func(*args, **kwargs)

    return _traced_send


def _start_consume_span_with_extracted_context(
    tracer: Tracer,
    context_manager: KafkaInstrumentorContextManager,
    instance: KafkaConsumer,
    headers: List,
    topic: str,
) -> Span:
    extracted_context = extract(headers, getter=_kafka_getter)
    span_name = _get_span_name("receive", topic)
    span = tracer.start_span(
        span_name, context=extracted_context, kind=trace.SpanKind.CONSUMER
    )
    new_context = set_span_in_context(span, extracted_context)
    context_manager.set_consumer_context(instance, new_context, span)
    return span


def _wrap_next(
    tracer: Tracer,
    context_manager: KafkaInstrumentorContextManager,
    consume_hook: HookT,
) -> Callable:
    def _traced_next(func, instance, args, kwargs):
        # End the current span if exists before processing the next record
        context_manager.close(instance)

        record = func(*args, **kwargs)

        if record:
            headers = record.headers
            topic = record.topic
            bootstrap_servers = (
                KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            )
            partition = record.partition
            span = _start_consume_span_with_extracted_context(
                tracer, context_manager, instance, headers, topic
            )
            with trace.use_span(span):
                _enrich_span(span, bootstrap_servers, topic, partition)
                try:
                    consume_hook(span, args, kwargs)
                except Exception as hook_exception:  # pylint: disable=W0703
                    _LOG.exception(hook_exception)
        # We do not close the current span when returning to the caller,
        # so the message processing logic will have the kafka span as parent
        return record

    return _traced_next
