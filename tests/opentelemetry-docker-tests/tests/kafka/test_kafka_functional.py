# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os

from kafka import KafkaAdminClient, KafkaProducer
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.kafka import KafkaInstrumentor
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase

KAFKA_HOST = os.getenv("KAFKA_HOST", "localhost")
KAFKA_PORT = int(os.getenv("KAFKA_PORT", "9092"))
KAFKA_BOOTSTRAP_SERVERS = f"{KAFKA_HOST}:{KAFKA_PORT}"
KAFKA_TOPIC = "otel-partition-test"
KAFKA_PARTITION_COUNT = 8


class TestFunctionalKafka(TestBase):
    @classmethod
    def setUpClass(cls):
        admin = KafkaAdminClient(bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS])
        try:
            admin.create_topics(
                [
                    NewTopic(
                        KAFKA_TOPIC,
                        num_partitions=KAFKA_PARTITION_COUNT,
                        replication_factor=1,
                    )
                ]
            )
        except TopicAlreadyExistsError:
            pass
        finally:
            admin.close()

    def setUp(self):
        super().setUp()
        KafkaInstrumentor().instrument(tracer_provider=self.tracer_provider)
        self.producer = KafkaProducer(bootstrap_servers=[KAFKA_BOOTSTRAP_SERVERS])

    def tearDown(self):
        self.producer.close()
        KafkaInstrumentor().uninstrument()
        super().tearDown()

    def test_send_records_delivered_partition(self):
        """The partition recorded on the span must match the partition the
        broker actually delivered the message to, read back from the
        ``send()`` future rather than recomputed with the partitioner."""
        futures = [self.producer.send(KAFKA_TOPIC, b"payload-%d" % index) for index in range(20)]
        metadatas = [future.get(timeout=30) for future in futures]

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), len(metadatas))
        for span, metadata in zip(spans, metadatas):
            self.assertEqual(span.name, f"{KAFKA_TOPIC} send")
            self.assertIs(span.kind, trace_api.SpanKind.PRODUCER)
            self.assertEqual(
                span.attributes[messaging_attributes.MESSAGING_SYSTEM],
                "kafka",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.MESSAGING_DESTINATION],
                KAFKA_TOPIC,
            )
            partition = span.attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION]
            self.assertIsInstance(partition, int)
            self.assertEqual(partition, metadata.partition)

    def test_send_with_explicit_partition(self):
        explicit_partition = KAFKA_PARTITION_COUNT - 1
        future = self.producer.send(KAFKA_TOPIC, b"payload", partition=explicit_partition)
        metadata = future.get(timeout=30)

        self.assertEqual(metadata.partition, explicit_partition)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION],
            explicit_partition,
        )
