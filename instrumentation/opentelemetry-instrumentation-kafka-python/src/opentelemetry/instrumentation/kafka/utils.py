# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json
from logging import getLogger
from typing import Callable, Dict, List, Optional

from kafka.record.abc import ABCRecord

from opentelemetry import context, propagate, trace
from opentelemetry.propagators import textmap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


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
        return KafkaPropertiesExtractor._extract_argument(
            "topic", 0, "unknown", args, kwargs
        )

    @staticmethod
    def extract_send_value(args, kwargs):
        """extract value from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "value", 1, None, args, kwargs
        )

    @staticmethod
    def extract_send_key(args, kwargs):
        """extract key from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "key", 2, None, args, kwargs
        )

    @staticmethod
    def extract_send_headers(args, kwargs):
        """extract headers from `send` method arguments in KafkaProducer class"""
        return KafkaPropertiesExtractor._extract_argument(
            "headers", 3, None, args, kwargs
        )

    @staticmethod
    def extract_send_partition(future) -> int | None:
        """Return the partition a message was actually assigned to.

        ``KafkaProducer.send()`` resolves the destination partition internally
        (running the partitioner exactly once) and exposes it on the returned
        ``FutureRecordMetadata`` via ``_produce_future.topic_partition``. Reading
        it back from the future is accurate for every case — explicit partition,
        key-based, and the random keyless case.

        The previous implementation estimated the partition *before* ``send()``
        by calling ``instance._partition()`` itself; with the default
        partitioner and no key that runs a random choice, which ``send()`` then
        redoes, so the recorded value frequently did not match where the message
        actually landed. See
        https://github.com/open-telemetry/opentelemetry-python-contrib/issues/4625
        """
        try:
            return future._produce_future.topic_partition[1]
        except (AttributeError, IndexError, TypeError) as exception:
            _LOG.debug("Unable to extract partition: %s", exception)
            return None


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
    span,
    bootstrap_servers: list[str],
    topic: str,
    partition: int | None,
):
    if span.is_recording():
        span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "kafka")
        span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)
        if partition is not None:
            span.set_attribute(
                SpanAttributes.MESSAGING_KAFKA_PARTITION, partition
            )
        span.set_attribute(
            SpanAttributes.MESSAGING_URL, json.dumps(bootstrap_servers)
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
        bootstrap_servers = KafkaPropertiesExtractor.extract_bootstrap_servers(
            instance
        )
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
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
            _enrich_span(span, bootstrap_servers, topic, partition)
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
):
    span_name = _get_span_name("receive", record.topic)
    with tracer.start_as_current_span(
        span_name,
        context=extracted_context,
        kind=trace.SpanKind.CONSUMER,
    ) as span:
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
        _enrich_span(span, bootstrap_servers, record.topic, record.partition)
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
            bootstrap_servers = (
                KafkaPropertiesExtractor.extract_bootstrap_servers(instance)
            )

            extracted_context = propagate.extract(
                record.headers, getter=_kafka_getter
            )
            _create_consumer_span(
                tracer,
                consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                args,
                kwargs,
            )
        return record

    return _traced_next
