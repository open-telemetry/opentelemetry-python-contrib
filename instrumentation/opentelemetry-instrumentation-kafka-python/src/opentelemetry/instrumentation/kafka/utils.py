# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import suppress
from logging import getLogger

from kafka.record.abc import ABCRecord

from opentelemetry import context, propagate, trace
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        return instance.config.get("bootstrap_servers")

    @staticmethod
    def extract_client_id(instance):
        return instance.config.get("client_id")

    @staticmethod
    def extract_consumer_group(instance):
        return instance.config.get("group_id")

    @staticmethod
    def _extract_argument(key, position, default_value, args, kwargs):
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_send_topic(args, kwargs):
        """extract topic from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument("topic", 0, "unknown", args, kwargs)

    @staticmethod
    def extract_send_key(args, kwargs):
        """extract key from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument("key", 2, None, args, kwargs)

    @staticmethod
    def extract_send_headers(args, kwargs):
        """extract headers from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument("headers", 3, None, args, kwargs)

    @staticmethod
    def extract_send_partition(future) -> int | None:
        """Extract the assigned partition from the future returned by `send`.

        `send()` resolves the partition internally (randomly for keyless
        messages), so it must be read back from the future rather than
        recomputed with the partitioner.
        """
        try:
            return future._produce_future.topic_partition[1]
        except (AttributeError, IndexError, TypeError) as exception:
            _LOG.debug("Unable to extract partition: %s", exception)
            return None


def _key_to_str(key) -> str | None:
    if key is None:
        return None

    if isinstance(key, bytes):
        with suppress(UnicodeDecodeError):
            return key.decode()

    return str(key)


ProduceHookT = Callable[[Span, list, dict], None] | None
ConsumeHookT = Callable[[Span, ABCRecord, list, dict], None] | None


class KafkaContextGetter(textmap.Getter[textmap.CarrierT]):
    def get(self, carrier: textmap.CarrierT, key: str) -> list[str] | None:
        if carrier is None:
            return None

        for item_key, value in carrier:
            if item_key == key:
                if value is not None:
                    return [value.decode()]
        return None

    def keys(self, carrier: textmap.CarrierT) -> list[str]:
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


def _enrich_base_span(
    span: Span,
    *,
    bootstrap_servers,
    client_id: str | None,
    topic: str,
    partition: int | None,
    key: str | None,
) -> None:
    span.set_attribute(
        messaging_attributes.MESSAGING_SYSTEM,
        messaging_attributes.MessagingSystemValues.KAFKA.value,
    )
    span.set_attribute(server_attributes.SERVER_ADDRESS, json.dumps(bootstrap_servers))
    if client_id is not None:
        span.set_attribute(messaging_attributes.MESSAGING_CLIENT_ID, client_id)
    span.set_attribute(messaging_attributes.MESSAGING_DESTINATION_NAME, topic)

    if partition is not None:
        span.set_attribute(
            messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID,
            str(partition),
        )

    if key is not None:
        span.set_attribute(messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY, key)


def _enrich_send_span(
    span: Span,
    *,
    bootstrap_servers,
    client_id: str | None,
    topic: str,
    partition: int | None,
    key: str | None,
) -> None:
    if not span.is_recording():
        return

    _enrich_base_span(
        span,
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        topic=topic,
        partition=partition,
        key=key,
    )

    span.set_attribute(messaging_attributes.MESSAGING_OPERATION_NAME, "send")
    span.set_attribute(
        messaging_attributes.MESSAGING_OPERATION_TYPE,
        messaging_attributes.MessagingOperationTypeValues.PUBLISH.value,
    )


def _enrich_consume_span(
    span: Span,
    *,
    bootstrap_servers,
    client_id: str | None,
    consumer_group: str | None,
    topic: str,
    partition: int | None,
    key: str | None,
    offset: int,
) -> None:
    if not span.is_recording():
        return

    _enrich_base_span(
        span,
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        topic=topic,
        partition=partition,
        key=key,
    )

    if consumer_group is not None:
        span.set_attribute(messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME, consumer_group)

    span.set_attribute(messaging_attributes.MESSAGING_OPERATION_NAME, "receive")
    span.set_attribute(
        messaging_attributes.MESSAGING_OPERATION_TYPE,
        messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
    )

    span.set_attribute(messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET, offset)

    # https://stackoverflow.com/questions/65935155/identify-and-find-specific-message-in-kafka-topic
    # A message within Kafka is uniquely defined by its topic name, topic partition and offset.
    if partition is not None:
        span.set_attribute(
            messaging_attributes.MESSAGING_MESSAGE_ID,
            f"{topic}.{partition}.{offset}",
        )


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"


def _wrap_send(tracer: Tracer, produce_hook: ProduceHookT) -> Callable:
    def _traced_send(func, instance, args, kwargs):
        headers = KafkaPropertiesExtractor.extract_send_headers(args, kwargs)
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = KafkaPropertiesExtractor.extract_send_topic(args, kwargs)
        bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
        client_id = KafkaPropertiesExtractor.extract_client_id(instance)
        key = _key_to_str(KafkaPropertiesExtractor.extract_send_key(args, kwargs))
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(span_name, kind=trace.SpanKind.PRODUCER) as span:
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

            future = func(*args, **kwargs)
            partition = KafkaPropertiesExtractor.extract_send_partition(future)
            _enrich_send_span(
                span,
                bootstrap_servers=bootstrap_servers,
                client_id=client_id,
                topic=topic,
                partition=partition,
                key=key,
            )
            return future

    return _traced_send


def _create_consumer_span(
    tracer,
    consume_hook,
    record,
    extracted_context,
    bootstrap_servers,
    client_id,
    consumer_group,
    args,
    kwargs,
):
    span_name = _get_span_name("receive", record.topic)
    with tracer.start_as_current_span(
        span_name,
        context=extracted_context,
        kind=trace.SpanKind.CONSUMER,
    ) as span:
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
        _enrich_consume_span(
            span,
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            consumer_group=consumer_group,
            topic=record.topic,
            partition=record.partition,
            key=_key_to_str(record.key),
            offset=record.offset,
        )
        try:
            if callable(consume_hook):
                consume_hook(span, record, args, kwargs)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        if token:
            context.detach(token)


def _wrap_next(
    tracer: Tracer,
    consume_hook: ConsumeHookT,
) -> Callable:
    def _traced_next(func, instance, args, kwargs):
        record = func(*args, **kwargs)

        if record:
            bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            client_id = KafkaPropertiesExtractor.extract_client_id(instance)
            consumer_group = KafkaPropertiesExtractor.extract_consumer_group(instance)

            extracted_context = propagate.extract(record.headers, getter=_kafka_getter)
            _create_consumer_span(
                tracer,
                consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                client_id,
                consumer_group,
                args,
                kwargs,
            )
        return record

    return _traced_next
