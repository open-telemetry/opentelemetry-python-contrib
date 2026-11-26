# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from os import environ
from unittest import mock

from kafka import KafkaConsumer, KafkaProducer

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.kafka import KafkaInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

_TOPIC: str = "test_topic"
_PARTITION: int = 3
_BOOTSTRAP_SERVERS: list[str] = ["localhost:9092"]
_BOOTSTRAP_SERVERS_JSON: str = '["localhost:9092"]'
_HOST: str = "localhost"
_PORT: int = 9092
_LEGACY_SCHEMA_URL: str = "https://opentelemetry.io/schemas/1.11.0"
_MESSAGING_SCHEMA_URL: str = "https://opentelemetry.io/schemas/1.44.0"

_OLD_ATTRIBUTES: set[str] = {
    SpanAttributes.MESSAGING_DESTINATION,
    SpanAttributes.MESSAGING_KAFKA_PARTITION,
    SpanAttributes.MESSAGING_URL,
}
_NEW_ATTRIBUTES: set[str] = {
    messaging_attributes.MESSAGING_DESTINATION_NAME,
    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID,
    messaging_attributes.MESSAGING_OPERATION_NAME,
    messaging_attributes.MESSAGING_OPERATION_TYPE,
    server_attributes.SERVER_ADDRESS,
    server_attributes.SERVER_PORT,
}


def _do_nothing(*args: object, **kwargs: object) -> None:
    """Stand in for ``KafkaProducer.close``.

    ``KafkaProducer.__del__`` calls it, and the producer below is built with
    ``__new__`` and a config holding only ``bootstrap_servers``, so the real
    one raises out of the garbage collector.
    """


class TestMessagingSemanticConventionOptIn(TestBase):
    def setUp(self) -> None:
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def tearDown(self) -> None:
        super().tearDown()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def produce_and_consume(self, opt_in: str | None) -> tuple[ReadableSpan, ReadableSpan]:
        """Instrument kafka-python with ``OTEL_SEMCONV_STABILITY_OPT_IN`` set to
        ``opt_in``, send and receive one message, and return the producer span
        and the consumer span that it emitted.

        ``opt_in`` of ``None`` leaves the environment variable unset, which is
        the default mode.
        """
        record = mock.MagicMock()
        record.topic = _TOPIC
        record.partition = _PARTITION
        record.headers = []

        overrides = {} if opt_in is None else {OTEL_SEMCONV_STABILITY_OPT_IN: opt_in}
        with mock.patch.dict("os.environ", overrides):
            if opt_in is None:
                environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)

            with (
                mock.patch.object(KafkaProducer, "send", autospec=True) as send,
                mock.patch.object(KafkaConsumer, "__next__", autospec=True) as next_record,
            ):
                send.return_value._produce_future.topic_partition = (
                    _TOPIC,
                    _PARTITION,
                )
                next_record.return_value = record

                instrumentor = KafkaInstrumentor()
                instrumentor.instrument(tracer_provider=self.tracer_provider)
                try:
                    producer = KafkaProducer.__new__(KafkaProducer)
                    producer.config = {"bootstrap_servers": _BOOTSTRAP_SERVERS}
                    producer.close = _do_nothing
                    producer.send(_TOPIC, b"value")

                    consumer = KafkaConsumer.__new__(KafkaConsumer)
                    consumer.config = {"bootstrap_servers": _BOOTSTRAP_SERVERS}
                    next(consumer)
                finally:
                    instrumentor.uninstrument()

        producer_span, consumer_span = self.memory_exporter.get_finished_spans()
        self.assertEqual(producer_span.kind, SpanKind.PRODUCER)
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        return producer_span, consumer_span

    def test_default_mode_emits_only_the_old_attributes(self) -> None:
        spans = self.produce_and_consume(None)

        for span in spans:
            self.assertEqual(span.instrumentation_scope.schema_url, _LEGACY_SCHEMA_URL)
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_SYSTEM],
                messaging_attributes.MessagingSystemValues.KAFKA.value,
            )
            self.assertEqual(span.attributes[SpanAttributes.MESSAGING_DESTINATION], _TOPIC)
            self.assertEqual(
                span.attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION],
                _PARTITION,
            )
            self.assertIsInstance(
                span.attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION],
                int,
            )
            self.assertEqual(
                span.attributes[SpanAttributes.MESSAGING_URL],
                _BOOTSTRAP_SERVERS_JSON,
            )
            self.assertEqual(_NEW_ATTRIBUTES & set(span.attributes), set())

    def test_messaging_mode_emits_only_the_stable_attributes(self) -> None:
        producer_span, consumer_span = self.produce_and_consume("messaging")
        operations = (
            (
                producer_span,
                messaging_attributes.MessagingOperationTypeValues.SEND.value,
            ),
            (
                consumer_span,
                messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
            ),
        )

        for span, operation in operations:
            self.assertEqual(span.instrumentation_scope.schema_url, _MESSAGING_SCHEMA_URL)
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_SYSTEM],
                messaging_attributes.MessagingSystemValues.KAFKA.value,
            )
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_DESTINATION_NAME],
                _TOPIC,
            )
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID],
                str(_PARTITION),
            )
            self.assertIsInstance(
                span.attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID],
                str,
            )
            self.assertEqual(span.attributes[server_attributes.SERVER_ADDRESS], _HOST)
            self.assertEqual(span.attributes[server_attributes.SERVER_PORT], _PORT)
            self.assertIsInstance(span.attributes[server_attributes.SERVER_PORT], int)
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_OPERATION_NAME],
                operation,
            )
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_OPERATION_TYPE],
                operation,
            )
            self.assertEqual(_OLD_ATTRIBUTES & set(span.attributes), set())

    def test_dup_mode_emits_both_generations_of_attributes(self) -> None:
        spans = self.produce_and_consume("messaging/dup")

        for span in spans:
            self.assertEqual(span.instrumentation_scope.schema_url, _MESSAGING_SCHEMA_URL)
            self.assertTrue(_OLD_ATTRIBUTES.issubset(span.attributes))
            self.assertTrue(_NEW_ATTRIBUTES.issubset(span.attributes))
            self.assertEqual(
                span.attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION],
                _PARTITION,
            )
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID],
                str(_PARTITION),
            )
