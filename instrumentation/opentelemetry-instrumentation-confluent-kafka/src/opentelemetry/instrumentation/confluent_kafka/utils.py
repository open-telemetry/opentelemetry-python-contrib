# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time
from logging import getLogger
from typing import Any

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
    return getattr(instance, "_producer", None) or getattr(instance, "_consumer", None) or instance


# list_topics() always issues a metadata request, so the timeout must be
# positive; with timeout=0 it expires before the broker can answer and no
# cluster id is ever returned.
_CLUSTER_ID_METADATA_TIMEOUT_SECS = 1.0
_CLUSTER_ID_FAILURE_BACKOFF_SECS = 300  # 5 minutes

# Shared by clients pointed at the same brokers. Populated by producers, which
# are the only clients that may ask for metadata (see _extract_cluster_id).
_cluster_id_by_bootstrap: dict[str, str] = {}


def _remember(instance: Any, name: str, value: Any) -> None:
    # The instrumentation wrappers are Python subclasses and hold attributes;
    # confluent_kafka's own C types accept neither attributes nor weak
    # references, so their per-instance cache is simply skipped.
    try:
        setattr(instance, name, value)
    except AttributeError:
        pass


def _extract_cluster_id(
    instance: Any,
    bootstrap_servers: str | None = None,
    topic: str | None = None,
) -> str | None:
    """Return the cluster id, asking the broker at most once per client.

    A metadata round trip costs far more than the produce it would annotate, so
    the result is cached on the client and shared with clients on the same
    bootstrap address. ``instance`` is the instrumentation wrapper that holds
    the cache; the metadata call goes to the client it wraps.
    """
    if instance is None:
        return None

    cluster_id: str | None = getattr(instance, "_otel_cluster_id", None)
    if cluster_id:
        return cluster_id

    if bootstrap_servers:
        cluster_id = _cluster_id_by_bootstrap.get(bootstrap_servers)
        if cluster_id:
            _remember(instance, "_otel_cluster_id", cluster_id)
            return cluster_id

    client = _get_real_instance(instance)

    # Naming a topic the client is not already connected to makes librdkafka hold
    # a handle for it and keep refreshing it for the life of the client (librdkafka
    # #4214, still open). The topic passed here is one the client already holds --
    # the one being produced to, or the one a record just arrived from -- so the
    # request adds no handle. A consumer with no topic in hand asks for nothing
    # rather than falling back to a whole-cluster query.
    if topic is None and getattr(client, "flush", None) is None:
        return None

    failure_time = getattr(instance, "_otel_cluster_id_failure_time", None)
    if failure_time is not None and time.monotonic() - failure_time < _CLUSTER_ID_FAILURE_BACKOFF_SECS:
        return None

    list_topics = getattr(client, "list_topics", None)
    if list_topics is None:
        return None

    try:
        # Scoped to one topic when we know it: cheaper than describing every
        # topic in the cluster.
        if topic:
            cluster_metadata = list_topics(topic=topic, timeout=_CLUSTER_ID_METADATA_TIMEOUT_SECS)
        else:
            cluster_metadata = list_topics(timeout=_CLUSTER_ID_METADATA_TIMEOUT_SECS)
        cluster_id = getattr(cluster_metadata, "cluster_id", None) or None
    except Exception:  # pylint: disable=broad-except
        cluster_id = None

    if cluster_id:
        _remember(instance, "_otel_cluster_id", cluster_id)
        if bootstrap_servers:
            _cluster_id_by_bootstrap[bootstrap_servers] = cluster_id
        return cluster_id

    # Retry on a timer rather than on the next span.
    _remember(instance, "_otel_cluster_id_failure_time", time.monotonic())
    return None


class KafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        config = getattr(instance, "config", None)
        if not isinstance(config, dict):
            return None
        # "metadata.broker.list" is librdkafka's legacy alias for
        # "bootstrap.servers"; "bootstrap_servers" is accepted for robustness.
        servers = (
            config.get("bootstrap.servers") or config.get("metadata.broker.list") or config.get("bootstrap_servers")
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
    partition: int | None = None,
    offset: int | None = None,
    operation: MessagingOperationTypeValues | None = None,
    bootstrap_servers: str | None = None,
    instance: Any | None = None,
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
    else:
        span.set_attribute(SpanAttributes.MESSAGING_TEMP_DESTINATION, True)

    _set_bootstrap_servers_attributes(span, bootstrap_servers)

    cluster_id = _extract_cluster_id(instance, bootstrap_servers, topic)
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
