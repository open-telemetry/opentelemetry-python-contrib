# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from logging import getLogger
from typing import Any, List, Optional

from opentelemetry import context, propagate
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION,
    MESSAGING_SYSTEM,
    MessagingOperationTypeValues,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.trace import Link, SpanKind

_LOG = getLogger(__name__)

# TODO(semconv #3819): once generated in opentelemetry-semantic-conventions,
# use messaging_attributes.MESSAGING_KAFKA_CLUSTER_ID instead of this literal.
_MESSAGING_KAFKA_CLUSTER_ID = "messaging.kafka.cluster.id"


def _get_real_instance(instance: Any) -> Any:
    """Unwrap Proxied* wrappers to get the underlying confluent-kafka Producer/Consumer."""
    return (
        getattr(instance, "_producer", None)
        or getattr(instance, "_consumer", None)
        or instance
    )


# Process-wide cache keyed by bootstrap.servers string; populated by producer spans so
# consumer spans can report cluster_id without calling list_topics() themselves.
_cluster_id_by_bootstrap: dict[str, str] = {}


def _extract_cluster_id(
    instance: Any, bootstrap_servers: Optional[str] = None
) -> Optional[str]:
    """Read cluster_id for span enrichment.

    Producers call list_topics(timeout=0) — reads librdkafka's in-process metadata
    cache, no I/O — and the result is stored in _cluster_id_by_bootstrap.
    Consumers never call list_topics(); they look up that cache by bootstrap
    address.  Calling list_topics() on a consumer is unsafe due to librdkafka
    UAF bug #4214.
    """
    if instance is None:
        return None
    if hasattr(instance, "flush"):
        # Producer: list_topics() is safe here.
        try:
            cluster_metadata = instance.list_topics(timeout=0)
            cluster_id = getattr(cluster_metadata, "cluster_id", None) or None
            if cluster_id and bootstrap_servers:
                _cluster_id_by_bootstrap[bootstrap_servers] = cluster_id
            return cluster_id
        except Exception:  # pylint: disable=broad-except
            return None
    # Consumer: never call list_topics() — librdkafka UAF bug #4214.
    if bootstrap_servers:
        return _cluster_id_by_bootstrap.get(bootstrap_servers)
    return None


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        config = getattr(instance, "config", None)
        if not isinstance(config, dict):
            return None
        # confluent-kafka uses the dotted key "bootstrap.servers"; also accept
        # the python-style "bootstrap_servers" for robustness.
        servers = config.get("bootstrap.servers") or config.get(
            "bootstrap_servers"
        )
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
    def extract_produce_headers(args, kwargs):
        """extract headers from `produce` method arguments in Producer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "headers", 6, None, args, kwargs
        )


class KafkaContextGetter(textmap.Getter):
    def get(self, carrier: textmap.CarrierT, key: str) -> Optional[List[str]]:
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

    def keys(self, carrier: textmap.CarrierT) -> List[str]:
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


def _create_new_consume_span(instance, tracer, records):
    links = _get_links_from_records(records)
    instance._current_consume_span = tracer.start_span(
        name=f"{records[0].topic()} process",
        links=links,
        kind=SpanKind.CONSUMER,
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


def _set_bootstrap_servers_attributes(span, bootstrap_servers):
    """Populate server.address and server.port from a bootstrap.servers
    string (e.g. ``host1:9092,host2:9092``)."""
    if not bootstrap_servers:
        return

    first_broker = bootstrap_servers.split(",")[0].strip()
    if not first_broker:
        return

    if ":" in first_broker:
        host, _, port = first_broker.rpartition(":")
        span.set_attribute(SERVER_ADDRESS, host)
        try:
            span.set_attribute(SERVER_PORT, int(port))
        except ValueError:
            # Port wasn't numeric; skip rather than emit a bad attribute.
            _LOG.debug("non-numeric port in bootstrap.servers: %r", port)
    else:
        span.set_attribute(SERVER_ADDRESS, first_broker)


def _enrich_span(
    span,
    topic,
    partition: Optional[int] = None,
    offset: Optional[int] = None,
    operation: Optional[MessagingOperationTypeValues] = None,
    bootstrap_servers: Optional[str] = None,
    instance: Optional[Any] = None,
):
    if not span.is_recording():
        return

    span.set_attribute(MESSAGING_SYSTEM, "kafka")
    span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)

    if partition is not None:
        span.set_attribute(SpanAttributes.MESSAGING_KAFKA_PARTITION, partition)

    span.set_attribute(
        SpanAttributes.MESSAGING_DESTINATION_KIND,
        MessagingDestinationKindValues.QUEUE.value,
    )

    if operation:
        span.set_attribute(MESSAGING_OPERATION, operation.value)

    _set_bootstrap_servers_attributes(span, bootstrap_servers)

    cluster_id = _extract_cluster_id(instance, bootstrap_servers)
    if cluster_id:
        span.set_attribute(_MESSAGING_KAFKA_CLUSTER_ID, cluster_id)

    # https://stackoverflow.com/questions/65935155/identify-and-find-specific-message-in-kafka-topic
    # A message within Kafka is uniquely defined by its topic name, topic partition and offset.
    if partition is not None and offset is not None and topic:
        span.set_attribute(
            MESSAGING_MESSAGE_ID,
            f"{topic}.{partition}.{offset}",
        )


_kafka_setter = KafkaContextSetter()


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"
