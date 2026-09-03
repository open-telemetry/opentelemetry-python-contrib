# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Callable
from logging import getLogger

from kafka.record.abc import ABCRecord

from opentelemetry import context, propagate, trace
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)

# TODO(semconv #3819): once generated in opentelemetry-semantic-conventions,
# use messaging_attributes.MESSAGING_KAFKA_CLUSTER_ID instead of this literal.
_MESSAGING_KAFKA_CLUSTER_ID = "messaging.kafka.cluster.id"


def _get_cluster_metadata(instance):
    """Return the kafka-python ``ClusterMetadata`` for a producer or consumer.

    ``KafkaProducer`` exposes it as ``_metadata``; ``KafkaConsumer`` as
    ``_client.cluster``.
    """
    cluster = getattr(instance, "_metadata", None)
    if cluster is not None:
        return cluster
    return getattr(getattr(instance, "_client", None), "cluster", None)


def _patch_cluster_id_capture(instance) -> None:
    """Capture the cluster id from the client's own metadata responses.

    Reads from the client's already-resolved metadata; opens no extra broker
    connection. kafka-python < 2.1 does not persist ``cluster_id`` on
    ``ClusterMetadata``, but the ``MetadataResponse`` (v2+) passed to
    ``update_metadata`` carries it, so wrap ``update_metadata`` to store it.
    Guarded so each client's metadata object is patched at most once.
    """
    cluster = _get_cluster_metadata(instance)
    if cluster is None or getattr(cluster, "_otel_cluster_id_patched", False):
        return
    original_update = cluster.update_metadata

    def _patched_update(metadata):
        result = original_update(metadata)
        cluster_id = getattr(metadata, "cluster_id", None)
        if cluster_id:
            cluster.cluster_id = cluster_id
        return result

    cluster.update_metadata = _patched_update
    cluster._otel_cluster_id_patched = True


def _extract_cluster_id(instance) -> str | None:
    cluster_id = getattr(_get_cluster_metadata(instance), "cluster_id", None)
    return cluster_id if cluster_id else None


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


def _enrich_span(
    span,
    bootstrap_servers: list[str],
    topic: str,
    partition: int | None,
    cluster_id: str | None = None,
):
    if span.is_recording():
        span.set_attribute(messaging_attributes.MESSAGING_SYSTEM, "kafka")
        span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)
        if partition is not None:
            span.set_attribute(SpanAttributes.MESSAGING_KAFKA_PARTITION, partition)
        span.set_attribute(SpanAttributes.MESSAGING_URL, json.dumps(bootstrap_servers))
        if cluster_id:
            span.set_attribute(_MESSAGING_KAFKA_CLUSTER_ID, cluster_id)


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
            cluster_id = _extract_cluster_id(instance)
            _enrich_span(span, bootstrap_servers, topic, partition, cluster_id)
            return future

    return _traced_send


def _create_consumer_span(
    tracer,
    consume_hook,
    record,
    extracted_context,
    bootstrap_servers,
    cluster_id,
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
        _enrich_span(
            span,
            bootstrap_servers,
            record.topic,
            record.partition,
            cluster_id,
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
            cluster_id = _extract_cluster_id(instance)
            extracted_context = propagate.extract(record.headers, getter=_kafka_getter)
            _create_consumer_span(
                tracer,
                consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                cluster_id,
                args,
                kwargs,
            )
        return record

    return _traced_next
