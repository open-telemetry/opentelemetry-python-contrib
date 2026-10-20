# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from logging import getLogger

from opentelemetry import context, propagate
from opentelemetry.instrumentation._semconv import (
    _get_semconv_opt_in_modes,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _report_old,
    _set_messaging_destination,
    _set_messaging_operation,
    _set_messaging_temp_destination,
    _StabilityMode,
)
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_BATCH_MESSAGE_COUNT,
    MESSAGING_CONSUMER_GROUP_NAME,
    MESSAGING_DESTINATION_PARTITION_ID,
    MESSAGING_KAFKA_OFFSET,
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION_NAME,
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
from opentelemetry.trace import Link, SpanKind

_LOG = getLogger(__name__)


def _get_messaging_semconv_mode() -> _StabilityMode:
    """Return the current messaging semantic-convention stability mode.

    Resolved lazily on every call (rather than once at instrument time)
    because ``instrument_producer``/``instrument_consumer`` are static
    entry points that bypass ``_instrument()``.
    """
    return _get_semconv_opt_in_modes((_OpenTelemetryStabilitySignalType.MESSAGING,))[
        _OpenTelemetryStabilitySignalType.MESSAGING
    ]


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
    def extract_consumer_group(instance):
        config = getattr(instance, "config", None)
        if not isinstance(config, dict):
            return None
        # confluent-kafka uses the dotted key "group.id"; also accept the
        # python-style "group_id" for robustness.
        return config.get("group.id") or config.get("group_id")

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


def _set_operation_name(
    attributes: dict,
    operation: MessagingOperationTypeValues,
    sem_conv_opt_in_mode: _StabilityMode,
):
    if not _report_new(sem_conv_opt_in_mode):
        return
    # `messaging.operation.name` is required by the new conventions. The
    # span name already carries this value (`send` for produce spans,
    # `process` for consume spans).
    attributes[MESSAGING_OPERATION_NAME] = (
        MessagingOperationTypeValues.SEND.value
        if operation.value == MessagingOperationTypeValues.PUBLISH.value
        else operation.value
    )


def _set_partition(
    attributes: dict,
    partition: int | None,
    sem_conv_opt_in_mode: _StabilityMode,
):
    if partition is None:
        return
    if _report_old(sem_conv_opt_in_mode):
        attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION] = partition
    if _report_new(sem_conv_opt_in_mode):
        attributes[MESSAGING_DESTINATION_PARTITION_ID] = str(partition)


def _set_consumer_group(
    attributes: dict,
    consumer_group: str | None,
    sem_conv_opt_in_mode: _StabilityMode,
):
    if not consumer_group:
        return
    if _report_old(sem_conv_opt_in_mode):
        attributes[SpanAttributes.MESSAGING_KAFKA_CONSUMER_GROUP] = consumer_group
    if _report_new(sem_conv_opt_in_mode):
        attributes[MESSAGING_CONSUMER_GROUP_NAME] = consumer_group


def _set_new_mode_extras(
    attributes: dict,
    offset: int | None,
    message_count: int | None,
    sem_conv_opt_in_mode: _StabilityMode,
):
    if not _report_new(sem_conv_opt_in_mode):
        return
    if offset is not None:
        attributes[MESSAGING_KAFKA_OFFSET] = offset
    if message_count is not None:
        attributes[MESSAGING_BATCH_MESSAGE_COUNT] = message_count


def _enrich_span(
    span,
    topic,
    partition: int | None = None,
    offset: int | None = None,
    operation: MessagingOperationTypeValues | None = None,
    bootstrap_servers: str | None = None,
    consumer_group: str | None = None,
    message_count: int | None = None,
    sem_conv_opt_in_mode: _StabilityMode | None = None,
):
    if not span.is_recording():
        return

    if sem_conv_opt_in_mode is None:
        sem_conv_opt_in_mode = _get_messaging_semconv_mode()

    attributes: dict = {}

    attributes[MESSAGING_SYSTEM] = MessagingSystemValues.KAFKA.value

    _set_messaging_destination(attributes, topic, sem_conv_opt_in_mode)

    if operation:
        # The old `messaging.operation` value is passed to the shared
        # helper, which maps `publish` to the new `send` operation type.
        _set_messaging_operation(attributes, operation.value, sem_conv_opt_in_mode)
        _set_operation_name(attributes, operation, sem_conv_opt_in_mode)
    else:
        _set_messaging_temp_destination(attributes, True, sem_conv_opt_in_mode)

    if _report_old(sem_conv_opt_in_mode):
        attributes[SpanAttributes.MESSAGING_DESTINATION_KIND] = MessagingDestinationKindValues.QUEUE.value

    _set_partition(attributes, partition, sem_conv_opt_in_mode)
    _set_consumer_group(attributes, consumer_group, sem_conv_opt_in_mode)
    _set_new_mode_extras(attributes, offset, message_count, sem_conv_opt_in_mode)

    for key, value in attributes.items():
        span.set_attribute(key, value)

    _set_bootstrap_servers_attributes(span, bootstrap_servers)

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
