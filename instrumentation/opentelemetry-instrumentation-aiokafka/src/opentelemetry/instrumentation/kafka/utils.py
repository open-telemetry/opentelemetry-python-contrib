import json
from logging import getLogger
from typing import Any, Callable, Dict, List, Optional

from aiokafka import (
    AIOKafkaClient,
    AIOKafkaConsumer,
    AIOKafkaProducer,
    ConsumerRecord,
)
from kafka.record.abc import ABCRecord

from opentelemetry import context, propagate, trace
from opentelemetry.propagators import textmap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(client: AIOKafkaClient) -> List[str]:
        return [f"{url}:{port}" for url, port, *_ in client.hosts]

    @staticmethod
    def _extract_argument(
        key: str, position: int, default_value: Any, args: Any, kwargs: Any
    ):
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_send_topic(args: Any, kwargs: Any):
        """extract topic from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "topic", 0, "unknown", args, kwargs
        )

    @staticmethod
    def extract_send_value(args: Any, kwargs: Any):
        """extract value from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "value", 1, None, args, kwargs
        )

    @staticmethod
    def extract_send_key(args: Any, kwargs: Any):
        """extract key from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument("key", 2, None, args, kwargs)

    @staticmethod
    def extract_send_headers(args: Any, kwargs: Any):
        """extract headers from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "headers", 3, None, args, kwargs
        )

    @staticmethod
    def extract_send_partition(args: Any, kwargs: Any):
        return KafkaPropertiesExtractor._extract_argument(
            "partition", 4, None, args, kwargs
        )

    @staticmethod
    def extract_client_id(client: AIOKafkaClient):
        return client._client_id


ProduceHookT = Optional[Callable[[Span, List, Dict], None]]
ConsumeHookT = Optional[Callable[[Span, ABCRecord, List, Dict], None]]


class KafkaContextGetter(textmap.Getter[textmap.CarrierT]):
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


class KafkaContextSetter(textmap.Setter[textmap.CarrierT]):
    def set(self, carrier: textmap.CarrierT, key: str, value: str) -> None:
        if carrier is None or key is None:
            return

        if value:
            value = value.encode()
        carrier.append((key, value))


_kafka_getter = KafkaContextGetter()
_kafka_setter = KafkaContextSetter()


def _enrich_span(
    span: Span,
    bootstrap_servers: List[str],
    topic: str,
    partition: Optional[int],
    client_id: str,
):
    span.set_attributes(
        {
            SpanAttributes.MESSAGING_SYSTEM: "kafka",
            SpanAttributes.MESSAGING_DESTINATION: topic,
            SpanAttributes.MESSAGING_URL: json.dumps(bootstrap_servers),
            SpanAttributes.MESSAGING_DESTINATION_KIND: "topic",
            SpanAttributes.MESSAGING_KAFKA_CLIENT_ID: client_id,
        }
    )

    if span.is_recording():
        if partition is not None:
            span.set_attribute(SpanAttributes.MESSAGING_KAFKA_PARTITION, partition)


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"


def _wrap_send(tracer: Tracer, produce_hook: ProduceHookT) -> Callable:
    def _traced_send(func, instance: AIOKafkaProducer, args, kwargs):
        headers = KafkaPropertiesExtractor.extract_send_headers(args, kwargs)
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = KafkaPropertiesExtractor.extract_send_topic(args, kwargs)
        bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(
            instance.client
        )
        partition = KafkaPropertiesExtractor.extract_send_partition(args, kwargs)
        client_id = KafkaPropertiesExtractor.extract_client_id(instance.client)

        span_name = _get_span_name("publish", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            _enrich_span(span, bootstrap_servers, topic, partition, client_id)
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

        return func(*args, **kwargs)

    return _traced_send


def _wrap_anext(
    tracer: Tracer,
    consume_hook: ConsumeHookT,
) -> Callable:
    # noinspection PyProtectedMember
    async def _traced_anext(func, instance: AIOKafkaConsumer, args, kwargs):
        record: ConsumerRecord = await func(*args, **kwargs)
        bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(
            instance._client
        )
        client_id = KafkaPropertiesExtractor.extract_client_id(instance._client)
        extracted_context = propagate.extract(record.headers, getter=_kafka_getter)
        span_name = _get_span_name("receive", record.topic)

        with tracer.start_as_current_span(
            span_name,
            context=extracted_context,
            kind=trace.SpanKind.CONSUMER,
        ) as span:
            new_context = trace.set_span_in_context(span, extracted_context)
            token = context.attach(new_context)
            _enrich_span(
                span, bootstrap_servers, record.topic, record.partition, client_id
            )

            try:
                if callable(consume_hook):
                    consume_hook(span, record, args, kwargs)
            except Exception as hook_exception:
                _LOG.exception(hook_exception)
            context.detach(token)

        return record

    return _traced_anext
