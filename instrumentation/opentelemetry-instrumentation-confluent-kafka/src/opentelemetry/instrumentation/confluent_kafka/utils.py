# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import threading
import time
from logging import getLogger
from typing import Any, Dict, List, Optional

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

_MESSAGING_CLUSTER_ID = "messaging.kafka.cluster.id"

_CLUSTER_ID_TTL_SECONDS = 60 * 60

_kafka_cluster_id_cache: Dict[str, object] = {}
_kafka_cluster_id_lock = threading.Lock()
# Auth config stored from the first fetch per broker key; used for TTL re-fetches.
_kafka_cluster_id_config_cache: Dict[str, Optional[Dict[str, str]]] = {}


def _get_real_instance(instance: Any) -> Any:
    """Unwrap Proxied* wrappers to get the underlying confluent-kafka Producer/Consumer."""
    return (
        getattr(instance, "_producer", None)
        or getattr(instance, "_consumer", None)
        or instance
    )


def _bootstrap_cache_key(bootstrap_servers: Optional[str]) -> str:
    if not bootstrap_servers:
        return ""
    parts = [s.strip() for s in bootstrap_servers.split(",") if s.strip()]
    return ",".join(sorted(parts))


def _fetch_cluster_id_background(
    bootstrap_servers: Optional[str],
    base_config: Optional[Dict[str, str]] = None,
    instance: Optional[Any] = None,
) -> None:
    """Fetch cluster UUID in a daemon thread. Uses instance.list_topics() when available; falls back to AdminClient."""
    if not bootstrap_servers:
        return
    cache_key = _bootstrap_cache_key(bootstrap_servers)
    if not cache_key:
        return

    with _kafka_cluster_id_lock:
        if base_config is not None:
            _kafka_cluster_id_config_cache.setdefault(cache_key, base_config)
        resolved_config = (
            _kafka_cluster_id_config_cache.get(cache_key) or base_config
        )

        existing = _kafka_cluster_id_cache.get(cache_key)
        if isinstance(existing, tuple):
            if time.monotonic() - existing[1] <= _CLUSTER_ID_TTL_SECONDS:
                return  # still fresh; stale value stays until re-fetch succeeds
            # TTL expired — leave stale tuple in cache so callers get the old value
            # while the background refresh runs, then the refresh will overwrite it.
        elif existing is not None:
            return  # "" sentinel — first fetch already in progress
        else:
            _kafka_cluster_id_cache[cache_key] = (
                ""  # mark first fetch in-flight
            )

    def _run() -> None:
        try:
            if instance is not None:
                cluster_metadata = instance.list_topics(timeout=10)
            else:
                from confluent_kafka.admin import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
                    AdminClient,
                )

                admin = AdminClient(
                    {
                        **(resolved_config or {}),
                        "bootstrap.servers": bootstrap_servers,
                    }
                )
                try:
                    cluster_metadata = admin.list_topics(timeout=10)
                finally:
                    # confluent_kafka.AdminClient has no explicit close(); deleting the reference
                    # allows librdkafka to release native resources via __del__ rather than waiting for GC.
                    del admin
            cluster_id = getattr(cluster_metadata, "cluster_id", None)
            if cluster_id:
                with _kafka_cluster_id_lock:
                    _kafka_cluster_id_cache[cache_key] = (
                        cluster_id,
                        time.monotonic(),
                    )
            else:
                with _kafka_cluster_id_lock:
                    _kafka_cluster_id_cache.pop(cache_key, None)
        except Exception:  # pylint: disable=broad-except
            with _kafka_cluster_id_lock:
                _kafka_cluster_id_cache.pop(cache_key, None)

    thread = threading.Thread(
        target=_run, daemon=True, name="otel-confluent-kafka-cluster-id"
    )
    try:
        thread.start()
    except Exception:  # pylint: disable=broad-except
        with _kafka_cluster_id_lock:
            _kafka_cluster_id_cache.pop(cache_key, None)


def _get_cluster_id(bootstrap_servers: Optional[str]) -> Optional[str]:
    if not bootstrap_servers:
        return None
    cache_key = _bootstrap_cache_key(bootstrap_servers)
    val = _kafka_cluster_id_cache.get(cache_key)
    return val[0] if isinstance(val, tuple) else None


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

    _fetch_cluster_id_background(bootstrap_servers, instance=instance)
    cluster_id = _get_cluster_id(bootstrap_servers)
    if cluster_id:
        span.set_attribute(_MESSAGING_CLUSTER_ID, cluster_id)

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
