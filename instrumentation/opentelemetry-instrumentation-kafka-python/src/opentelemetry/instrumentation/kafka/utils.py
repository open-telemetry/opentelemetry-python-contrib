# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Callable
from logging import getLogger
from re import compile as re_compile
from socket import AF_INET6, inet_pton

from kafka.record.abc import ABCRecord

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation._semconv import (
    _report_new,
    _report_old,
    _StabilityMode,
)
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span
from opentelemetry.util.types import AttributeValue

_LOG = getLogger(__name__)

_SECURITY_PROTOCOL_PREFIX = re_compile("^.*://")


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
    def extract_send_topic(args, kwargs):
        """extract topic from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument("topic", 0, "unknown", args, kwargs)

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


def _bootstrap_servers_attributes(bootstrap_servers: str | list[str] | None) -> dict[str, AttributeValue]:
    """Derive ``server.address`` and ``server.port`` from kafka-python's
    ``bootstrap_servers``.

    The value is one ``host:port`` entry, a comma-separated string of them, or
    a list of them, and each entry may carry a leading security protocol as in
    ``SASL_SSL://broker:9093``. Only the first entry is reported, the way
    ``opentelemetry-instrumentation-confluent-kafka`` reports it. An entry
    carrying no port leaves ``server.port`` out rather than assuming 9092, so
    the span reports what was configured.
    """
    if not bootstrap_servers:
        return {}

    entries = bootstrap_servers.split(",") if isinstance(bootstrap_servers, str) else bootstrap_servers

    entry = ""
    for candidate in entries:
        entry = _SECURITY_PROTOCOL_PREFIX.sub("", str(candidate).strip())
        if entry:
            break

    if not entry:
        return {}

    if entry.startswith("["):
        host, _, rest = entry[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    elif ":" not in entry:
        host, port = entry, ""
    else:
        try:
            inet_pton(AF_INET6, entry)
        except (OSError, ValueError):
            host, _, port = entry.rpartition(":")
        else:
            host, port = entry, ""

    if not host:
        return {}

    attributes: dict[str, AttributeValue] = {server_attributes.SERVER_ADDRESS: host}
    if port.isdecimal():
        attributes[server_attributes.SERVER_PORT] = int(port)
    elif port:
        _LOG.debug("non-numeric port in bootstrap_servers: %r", port)
    return attributes


def _partition_attributes(partition: int, sem_conv_opt_in_mode: _StabilityMode) -> dict[str, AttributeValue]:
    """Return the partition attributes of each generation the mode asks for.

    The producer only learns the partition after ``send`` returns, so this is
    applied both when the span is created and afterwards.
    """
    attributes: dict[str, AttributeValue] = {}
    if _report_old(sem_conv_opt_in_mode):
        attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION] = partition
    if _report_new(sem_conv_opt_in_mode):
        attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID] = str(partition)
    return attributes


def _get_attributes(
    bootstrap_servers: str | list[str] | None,
    topic: str,
    operation: messaging_attributes.MessagingOperationTypeValues,
    sem_conv_opt_in_mode: _StabilityMode,
    partition: int | None = None,
) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {
        messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
    }

    if _report_old(sem_conv_opt_in_mode):
        attributes[SpanAttributes.MESSAGING_DESTINATION] = topic
        attributes[SpanAttributes.MESSAGING_URL] = json.dumps(bootstrap_servers)

    if _report_new(sem_conv_opt_in_mode):
        attributes[messaging_attributes.MESSAGING_DESTINATION_NAME] = topic
        attributes[messaging_attributes.MESSAGING_OPERATION_NAME] = operation.value
        attributes[messaging_attributes.MESSAGING_OPERATION_TYPE] = operation.value
        attributes.update(_bootstrap_servers_attributes(bootstrap_servers))

    if partition is not None:
        attributes.update(_partition_attributes(partition, sem_conv_opt_in_mode))

    return attributes


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"


def _wrap_send(
    tracer: Tracer,
    produce_hook: ProduceHookT,
    sem_conv_opt_in_mode: _StabilityMode,
) -> Callable:
    operation = messaging_attributes.MessagingOperationTypeValues.SEND

    def _traced_send(func, instance, args, kwargs):
        headers = KafkaPropertiesExtractor.extract_send_headers(args, kwargs)
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = KafkaPropertiesExtractor.extract_send_topic(args, kwargs)
        bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
        span_name = _get_span_name(operation.value, topic)
        attributes = _get_attributes(bootstrap_servers, topic, operation, sem_conv_opt_in_mode)
        with tracer.start_as_current_span(span_name, kind=trace.SpanKind.PRODUCER, attributes=attributes) as span:
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
            if partition is not None:
                for key, value in _partition_attributes(partition, sem_conv_opt_in_mode).items():
                    span.set_attribute(key, value)
            return future

    return _traced_send


def _create_consumer_span(
    tracer,
    consume_hook,
    record,
    extracted_context,
    bootstrap_servers,
    args,
    kwargs,
    sem_conv_opt_in_mode: _StabilityMode,
):
    operation = messaging_attributes.MessagingOperationTypeValues.RECEIVE
    span_name = _get_span_name(operation.value, record.topic)
    attributes = _get_attributes(
        bootstrap_servers,
        record.topic,
        operation,
        sem_conv_opt_in_mode,
        record.partition,
    )
    with tracer.start_as_current_span(
        span_name,
        context=extracted_context,
        kind=trace.SpanKind.CONSUMER,
        attributes=attributes,
    ) as span:
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
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
    sem_conv_opt_in_mode: _StabilityMode,
) -> Callable:
    def _traced_next(func, instance, args, kwargs):
        record = func(*args, **kwargs)

        if record:
            bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(instance)

            extracted_context = propagate.extract(record.headers, getter=_kafka_getter)
            _create_consumer_span(
                tracer,
                consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                args,
                kwargs,
                sem_conv_opt_in_mode,
            )
        return record

    return _traced_next
