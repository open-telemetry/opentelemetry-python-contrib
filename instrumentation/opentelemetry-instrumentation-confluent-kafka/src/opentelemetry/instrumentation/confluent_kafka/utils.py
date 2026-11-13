# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger
from typing import TYPE_CHECKING, Any

from opentelemetry import context, propagate
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION,
    MESSAGING_SYSTEM,
    MessagingOperationTypeValues,
    MessagingSystemValues,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.trace import Link, SpanKind, Tracer, get_current_span
from opentelemetry.util.types import Attributes, AttributeValue

if TYPE_CHECKING:
    from confluent_kafka import Message

_LOG = getLogger(__name__)


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        config = getattr(instance, "config", None)
        if not isinstance(config, dict):
            return None
        # confluent-kafka uses the dotted key "bootstrap.servers"; also accept
        # the python-style "bootstrap_servers" for robustness.
        servers = config.get("bootstrap.servers") or config.get("bootstrap_servers")
        if isinstance(servers, (list, tuple)):
            servers = ",".join(str(s) for s in servers)
        return servers

    @staticmethod
    def _extract_argument(key, position, default_value, args, kwargs):
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_produce_topic(args, kwargs):
        """extract topic from `produce` method arguments in Producer class"""
        return kwargs.get("topic") or (args[0] if args else "unknown")

    @staticmethod
    def extract_produce_partition(args, kwargs):
        """extract partition from `produce` method arguments in Producer class"""
        return KafkaPropertiesExtractor._extract_argument("partition", 3, None, args, kwargs)

    @staticmethod
    def extract_produce_headers(args, kwargs):
        """extract headers from `produce` method arguments in Producer class"""
        return KafkaPropertiesExtractor._extract_argument("headers", 6, None, args, kwargs)


class KafkaContextGetter(textmap.Getter):
    def get(self, carrier: textmap.CarrierT, key: str) -> list[str] | None:
        if carrier is None:
            return None

        carrier_items = carrier
        if isinstance(carrier, dict):
            carrier_items = carrier.items()

        for item_key, value in carrier_items:
            if item_key == key:
                if value is not None:
                    return [value.decode()]

        return None

    def keys(self, carrier: textmap.CarrierT) -> list[str]:
        if carrier is None:
            return []

        carrier_items = carrier
        if isinstance(carrier, dict):
            carrier_items = carrier.items()
        return [key for (key, value) in carrier_items]


class KafkaContextSetter(textmap.Setter):
    def set(self, carrier: textmap.CarrierT, key: str, value: str) -> None:
        if carrier is None or key is None:
            return

        if value:
            value = value.encode()

        if isinstance(carrier, list):
            carrier.append((key, value))

        if isinstance(carrier, dict):
            carrier[key] = value


_kafka_getter = KafkaContextGetter()


def _end_current_consume_span(instance):
    if instance._current_context_token:
        context.detach(instance._current_context_token)
    instance._current_context_token = None
    instance._current_consume_span.end()
    instance._current_consume_span = None


def _create_new_consume_span(
    instance: Any,
    tracer: Tracer,
    records: Sequence[Message],
    attributes: Attributes,
    use_message_context_as_parent: bool = False,
) -> None:
    # By default the process span takes the ambient context as parent and links
    # to the creation context of every record. Records in a batch can belong to
    # different traces, so a batch span never takes a record context as parent.
    # https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/#message-creation-context-as-parent-of-process-span
    ctx = None
    links: list[Link] = []

    if use_message_context_as_parent and len(records) == 1:
        message_ctx = propagate.extract(records[0].headers(), getter=_kafka_getter)
        message_span_context = get_current_span(message_ctx).get_span_context()
        if message_span_context.is_valid:
            # One record with a valid creation context: use it as parent, keep a
            # link to it, and link the ambient span to preserve that correlation.
            ctx = message_ctx
            links.append(Link(context=message_span_context))
            ambient_span_context = get_current_span().get_span_context()
            if ambient_span_context.is_valid:
                links.append(Link(context=ambient_span_context))

    if ctx is None:
        links = _get_links_from_records(records)

    instance._current_consume_span = tracer.start_span(
        name=f"{records[0].topic()} process",
        links=links,
        attributes=attributes,
        kind=SpanKind.CONSUMER,
        context=ctx,
    )


def _get_links_from_records(records):
    links = []
    for record in records:
        ctx = propagate.extract(record.headers(), getter=_kafka_getter)
        if ctx:
            for item in ctx.values():
                if hasattr(item, "get_span_context"):
                    links.append(Link(context=item.get_span_context()))

    return links


def _get_bootstrap_servers_attributes(bootstrap_servers: str | None) -> dict[str, AttributeValue]:
    """Collect server.address and server.port from the first bootstrap server."""
    attributes: dict[str, AttributeValue] = {}
    if not bootstrap_servers:
        return attributes

    first_broker = bootstrap_servers.split(",")[0].strip()
    if not first_broker:
        return attributes

    if ":" in first_broker:
        host, _, port = first_broker.rpartition(":")
        attributes[SERVER_ADDRESS] = host
        try:
            attributes[SERVER_PORT] = int(port)
        except ValueError:
            # Port wasn't numeric; skip rather than emit a bad attribute.
            _LOG.debug("non-numeric port in bootstrap.servers: %r", port)
    else:
        attributes[SERVER_ADDRESS] = first_broker
    return attributes


def _get_attributes(
    topic: str,
    partition: int | None = None,
    offset: int | None = None,
    operation: MessagingOperationTypeValues | None = None,
    bootstrap_servers: str | None = None,
) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {
        MESSAGING_SYSTEM: MessagingSystemValues.KAFKA.value,
        SpanAttributes.MESSAGING_DESTINATION: topic,
        SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
    }

    if partition is not None:
        attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION] = partition

    if offset is not None:
        attributes[SpanAttributes.MESSAGING_KAFKA_MESSAGE_OFFSET] = offset

    if operation:
        attributes[MESSAGING_OPERATION] = operation.value
    else:
        attributes[SpanAttributes.MESSAGING_TEMP_DESTINATION] = True

    attributes.update(_get_bootstrap_servers_attributes(bootstrap_servers))

    # https://stackoverflow.com/questions/65935155/identify-and-find-specific-message-in-kafka-topic
    # A message within Kafka is uniquely defined by its topic name, topic partition and offset.
    if partition is not None and offset is not None and topic:
        attributes[MESSAGING_MESSAGE_ID] = f"{topic}.{partition}.{offset}"

    return attributes


_kafka_setter = KafkaContextSetter()


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"
