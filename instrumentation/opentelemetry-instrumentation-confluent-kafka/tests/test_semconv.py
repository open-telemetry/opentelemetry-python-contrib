# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=no-name-in-module

import os
from unittest.mock import patch

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
)
from opentelemetry.instrumentation.confluent_kafka import (
    ConfluentKafkaInstrumentor,
)
from opentelemetry.instrumentation.confluent_kafka.utils import (
    KafkaPropertiesExtractor,
)
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_BATCH_MESSAGE_COUNT,
    MESSAGING_CONSUMER_GROUP_NAME,
    MESSAGING_DESTINATION_NAME,
    MESSAGING_DESTINATION_PARTITION_ID,
    MESSAGING_KAFKA_OFFSET,
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION,
    MESSAGING_OPERATION_NAME,
    MESSAGING_OPERATION_TYPE,
    MESSAGING_SYSTEM,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase

from .utils import MockConsumer, MockedMessage, MockedProducer


def stability_mode(mode):
    def decorator(test_case):
        @patch.dict(os.environ, {OTEL_SEMCONV_STABILITY_OPT_IN: mode})
        def wrapper(*args, **kwargs):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            try:
                return test_case(*args, **kwargs)
            finally:
                # Restore the default (old conventions) state so other
                # tests in the same process are not affected.
                _OpenTelemetrySemanticConventionStability._initialized = False
                os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
                _OpenTelemetrySemanticConventionStability._initialize()

        return wrapper

    return decorator


class TestConfluentKafkaSemConv(TestBase):
    def _produce_span(self):
        instrumentation = ConfluentKafkaInstrumentor()
        producer = MockedProducer(
            [],
            {"bootstrap.servers": "localhost:29092"},
        )
        producer = instrumentation.instrument_producer(producer)
        self.memory_exporter.clear()
        producer.produce(topic="topic-1", key="key-1", value="value-1")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        return spans[0]

    def _consume_span(self):
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [MockedMessage("topic-10", 2, 4, [])],
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        consumer = instrumentation.instrument_consumer(consumer)
        self.memory_exporter.clear()
        consumer.poll()
        # Second (empty) poll ends the in-flight process span.
        consumer.poll()
        spans = [span for span in self.memory_exporter.get_finished_spans() if span.name == "topic-10 process"]
        self.assertEqual(len(spans), 1)
        return spans[0]

    @stability_mode("")
    def test_producer_default_mode(self):
        span = self._produce_span()
        attrs = span.attributes
        self.assertEqual(span.name, "topic-1 send")
        self.assertEqual(attrs[MESSAGING_SYSTEM], "kafka")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION], "topic-1")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION_KIND], "queue")
        self.assertEqual(attrs[MESSAGING_OPERATION], "publish")
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 29092)
        self.assertNotIn(MESSAGING_DESTINATION_NAME, attrs)
        self.assertNotIn(MESSAGING_OPERATION_TYPE, attrs)
        self.assertNotIn(MESSAGING_OPERATION_NAME, attrs)

    @stability_mode("messaging")
    def test_producer_messaging_mode(self):
        span = self._produce_span()
        attrs = span.attributes
        self.assertEqual(span.name, "topic-1 send")
        self.assertEqual(attrs[MESSAGING_SYSTEM], "kafka")
        self.assertEqual(attrs[MESSAGING_DESTINATION_NAME], "topic-1")
        self.assertEqual(attrs[MESSAGING_OPERATION_TYPE], "send")
        self.assertEqual(attrs[MESSAGING_OPERATION_NAME], "send")
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 29092)
        self.assertNotIn(SpanAttributes.MESSAGING_DESTINATION, attrs)
        self.assertNotIn(SpanAttributes.MESSAGING_DESTINATION_KIND, attrs)
        self.assertNotIn(MESSAGING_OPERATION, attrs)

    @stability_mode("messaging/dup")
    def test_producer_messaging_dup_mode(self):
        span = self._produce_span()
        attrs = span.attributes
        self.assertEqual(span.name, "topic-1 send")
        # Old attributes are still emitted ...
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION], "topic-1")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION_KIND], "queue")
        self.assertEqual(attrs[MESSAGING_OPERATION], "publish")
        # ... alongside the new ones.
        self.assertEqual(attrs[MESSAGING_DESTINATION_NAME], "topic-1")
        self.assertEqual(attrs[MESSAGING_OPERATION_TYPE], "send")
        self.assertEqual(attrs[MESSAGING_OPERATION_NAME], "send")

    @stability_mode("")
    def test_consumer_default_mode(self):
        span = self._consume_span()
        attrs = span.attributes
        self.assertEqual(attrs[MESSAGING_SYSTEM], "kafka")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION], "topic-10")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION_KIND], "queue")
        self.assertEqual(attrs[MESSAGING_OPERATION], "process")
        partition = attrs[SpanAttributes.MESSAGING_KAFKA_PARTITION]
        self.assertEqual(partition, 2)
        self.assertIs(type(partition), int)
        self.assertEqual(attrs[SpanAttributes.MESSAGING_KAFKA_CONSUMER_GROUP], "mygroup")
        self.assertEqual(attrs[MESSAGING_MESSAGE_ID], "topic-10.2.4")
        self.assertNotIn(MESSAGING_DESTINATION_NAME, attrs)
        self.assertNotIn(MESSAGING_OPERATION_TYPE, attrs)
        self.assertNotIn(MESSAGING_OPERATION_NAME, attrs)
        self.assertNotIn(MESSAGING_DESTINATION_PARTITION_ID, attrs)
        self.assertNotIn(MESSAGING_CONSUMER_GROUP_NAME, attrs)
        self.assertNotIn(MESSAGING_KAFKA_OFFSET, attrs)

    @stability_mode("messaging")
    def test_consumer_messaging_mode(self):
        span = self._consume_span()
        attrs = span.attributes
        self.assertEqual(attrs[MESSAGING_SYSTEM], "kafka")
        self.assertEqual(attrs[MESSAGING_DESTINATION_NAME], "topic-10")
        self.assertEqual(attrs[MESSAGING_OPERATION_TYPE], "process")
        self.assertEqual(attrs[MESSAGING_OPERATION_NAME], "process")
        partition_id = attrs[MESSAGING_DESTINATION_PARTITION_ID]
        self.assertEqual(partition_id, "2")
        self.assertIs(type(partition_id), str)
        self.assertEqual(attrs[MESSAGING_CONSUMER_GROUP_NAME], "mygroup")
        offset = attrs[MESSAGING_KAFKA_OFFSET]
        self.assertEqual(offset, 4)
        self.assertIs(type(offset), int)
        self.assertEqual(attrs[MESSAGING_MESSAGE_ID], "topic-10.2.4")
        self.assertNotIn(SpanAttributes.MESSAGING_DESTINATION, attrs)
        self.assertNotIn(SpanAttributes.MESSAGING_DESTINATION_KIND, attrs)
        self.assertNotIn(MESSAGING_OPERATION, attrs)
        self.assertNotIn(SpanAttributes.MESSAGING_KAFKA_PARTITION, attrs)
        self.assertNotIn(SpanAttributes.MESSAGING_KAFKA_CONSUMER_GROUP, attrs)

    @stability_mode("messaging/dup")
    def test_consumer_messaging_dup_mode(self):
        span = self._consume_span()
        attrs = span.attributes
        # Old attributes are still emitted ...
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION], "topic-10")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_DESTINATION_KIND], "queue")
        self.assertEqual(attrs[MESSAGING_OPERATION], "process")
        self.assertEqual(attrs[SpanAttributes.MESSAGING_KAFKA_PARTITION], 2)
        self.assertEqual(attrs[SpanAttributes.MESSAGING_KAFKA_CONSUMER_GROUP], "mygroup")
        # ... alongside the new ones.
        self.assertEqual(attrs[MESSAGING_DESTINATION_NAME], "topic-10")
        self.assertEqual(attrs[MESSAGING_OPERATION_TYPE], "process")
        self.assertEqual(attrs[MESSAGING_OPERATION_NAME], "process")
        self.assertEqual(attrs[MESSAGING_DESTINATION_PARTITION_ID], "2")
        self.assertEqual(attrs[MESSAGING_CONSUMER_GROUP_NAME], "mygroup")
        self.assertEqual(attrs[MESSAGING_KAFKA_OFFSET], 4)
        self.assertEqual(attrs[MESSAGING_MESSAGE_ID], "topic-10.2.4")

    @stability_mode("messaging")
    def test_consume_batch_sets_message_count_in_messaging_mode(self):
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [
                MockedMessage("topic-1", 0, 0, []),
                MockedMessage("topic-1", 0, 1, []),
                MockedMessage("topic-1", 0, 2, []),
            ],
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        consumer = instrumentation.instrument_consumer(consumer)
        self.memory_exporter.clear()
        consumer.consume(3)
        # Empty consume ends the in-flight process span.
        consumer.consume(1)
        spans = [span for span in self.memory_exporter.get_finished_spans() if span.name == "topic-1 process"]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes[MESSAGING_BATCH_MESSAGE_COUNT], 3)
        # Batch spans describe multiple messages, so no per-message offset
        # or partition is reported for them.
        self.assertNotIn(MESSAGING_KAFKA_OFFSET, spans[0].attributes)

    @stability_mode("")
    def test_consume_batch_has_no_message_count_in_default_mode(self):
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [
                MockedMessage("topic-1", 0, 0, []),
                MockedMessage("topic-1", 0, 1, []),
            ],
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        consumer = instrumentation.instrument_consumer(consumer)
        self.memory_exporter.clear()
        consumer.consume(2)
        consumer.consume(1)
        spans = [span for span in self.memory_exporter.get_finished_spans() if span.name == "topic-1 process"]
        self.assertEqual(len(spans), 1)
        self.assertNotIn(MESSAGING_BATCH_MESSAGE_COUNT, spans[0].attributes)

    @stability_mode("")
    def test_schema_url_default_mode(self):
        self.assertEqual(
            _get_schema_url_for_signal_types([_OpenTelemetryStabilitySignalType.MESSAGING]),
            "https://opentelemetry.io/schemas/1.11.0",
        )

    @stability_mode("messaging")
    def test_schema_url_messaging_mode(self):
        self.assertEqual(
            _get_schema_url_for_signal_types([_OpenTelemetryStabilitySignalType.MESSAGING]),
            "https://opentelemetry.io/schemas/1.44.0",
        )

    @stability_mode("messaging/dup")
    def test_schema_url_messaging_dup_mode(self):
        self.assertEqual(
            _get_schema_url_for_signal_types([_OpenTelemetryStabilitySignalType.MESSAGING]),
            "https://opentelemetry.io/schemas/1.44.0",
        )

    def test_extract_consumer_group(self):
        class _Instance:
            def __init__(self, config):
                self.config = config

        self.assertEqual(
            KafkaPropertiesExtractor.extract_consumer_group(_Instance({"group.id": "g1"})),
            "g1",
        )
        self.assertEqual(
            KafkaPropertiesExtractor.extract_consumer_group(_Instance({"group_id": "g2"})),
            "g2",
        )
        self.assertIsNone(KafkaPropertiesExtractor.extract_consumer_group(_Instance({})))
        self.assertIsNone(KafkaPropertiesExtractor.extract_consumer_group(_Instance(None)))
        self.assertIsNone(KafkaPropertiesExtractor.extract_consumer_group(object()))
