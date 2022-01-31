import json
from logging import getLogger
from typing import Callable, Dict, List, Optional

from confluent_kafka import Message

from opentelemetry import context, propagate, trace
from opentelemetry.propagators import textmap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        print(dir(instance))
        return instance.config.get("bootstrap.servers")

    @staticmethod
    def _extract_argument(key, position, default_value, args, kwargs):
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_produce_topic(args):
        """extract topic from `produce` method arguments in Producer class"""
        if len(args) > 0:
            return args[0]
        return "unknown"

    @staticmethod
    def extract_produce_value(args, kwargs):
        """extract value from `produce` method arguments in Producer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "value", 1, None, args, kwargs
        )

    @staticmethod
    def extract_produce_key(args, kwargs):
        """extract key from `produce` method arguments in Producer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "key", 2, None, args, kwargs
        )

    @staticmethod
    def extract_produce_headers(args, kwargs):
        """extract headers from `produce` method arguments in Producer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "headers", 6, None, args, kwargs
        )

    @staticmethod
    def extract_produce_partition(instance, args, kwargs):
        """extract partition `produce` method arguments, using the `_partition` method in Producer class"""
        topic = KafkaPropertiesExtractor.extract_produce_topic(args)
        key = KafkaPropertiesExtractor.extract_produce_key(args, kwargs)
        value = KafkaPropertiesExtractor.extract_produce_value(args, kwargs)
        partition = KafkaPropertiesExtractor._extract_argument(
            "partition", 3, None, args, kwargs
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

ProduceHookT = Optional[Callable[[Span, List, Dict], None]]
ConsumeHookT = Optional[Callable[[Span, Message, List, Dict], None]]

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

def _enrich_span(span, topic: str):
    if span.is_recording():
        span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "kafka")
        span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)

def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"

def _wrap_produce(tracer: Tracer, produce_hook: ProduceHookT) -> Callable:
    def _traced_produce(instance, *args, **kwargs):
        headers = KafkaPropertiesExtractor.extract_produce_headers(args, kwargs)
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = KafkaPropertiesExtractor.extract_produce_topic(args)
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            _enrich_span(span, topic)
            propagate.inject(
                headers,
                context=trace.set_span_in_context(span),
                setter=_kafka_setter,
            )
            try:
                if callable(produce_hook):
                    produce_hook(span, args, kwargs)
            except Exception as hook_exception:  # pylint: disable=W0703
                _LOG.exception(hook_exception)

        return instance.produce(*args, **kwargs)

    return _traced_produce

def _create_consumer_span(
    tracer,
    consume_hook,
    record,
    extracted_context,
    args,
    kwargs,
):
    span_name = _get_span_name("receive", record.topic())
    with tracer.start_as_current_span(
        span_name,
        context=extracted_context,
        kind=trace.SpanKind.CONSUMER,
    ) as span:
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
        _enrich_span(span, record.topic())
        try:
            if callable(consume_hook):
                consume_hook(span, record, args, kwargs)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        context.detach(token)


def _wrap_poll(tracer: Tracer, consume_hook: ConsumeHookT) -> Callable:
    def _traced_poll(instance, *args, **kwargs):
        record = instance.poll(*args, **kwargs)
        if record:
            extracted_context = propagate.extract(record.headers(), getter=_kafka_getter)
            _create_consumer_span(
                tracer,
                consume_hook,
                record,
                extracted_context,
                args,
                kwargs,
            )
        return record
    return _traced_poll
