# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=unnecessary-dunder-call

from types import SimpleNamespace
from unittest import TestCase, mock

from opentelemetry.instrumentation.kafka.utils import (
    KafkaPropertiesExtractor,
    _create_consumer_span,
    _get_span_name,
    _kafka_getter,
    _kafka_setter,
    _wrap_next,
    _wrap_send,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.trace import SpanKind


class TestUtils(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.topic_name = "test_topic"
        self.args = [self.topic_name]
        self.headers = []
        self.kwargs = {"partition": 0, "headers": self.headers}

    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers"
    )
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition"
    )
    @mock.patch("opentelemetry.instrumentation.kafka.utils._enrich_span")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    def test_wrap_send_with_topic_as_arg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.wrap_send_helper(
            inject,
            set_span_in_context,
            enrich_span,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers"
    )
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition"
    )
    @mock.patch("opentelemetry.instrumentation.kafka.utils._enrich_span")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    def test_wrap_send_with_topic_as_kwarg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.args = []
        self.kwargs["topic"] = self.topic_name
        self.wrap_send_helper(
            inject,
            set_span_in_context,
            enrich_span,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    def wrap_send_helper(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        produce_hook = mock.MagicMock()
        original_send_callback = mock.MagicMock()
        kafka_producer = mock.MagicMock()
        expected_span_name = _get_span_name("send", self.topic_name)

        wrapped_send = _wrap_send(tracer, produce_hook)
        retval = wrapped_send(
            original_send_callback, kafka_producer, self.args, self.kwargs
        )

        extract_bootstrap_servers.assert_called_once_with(kafka_producer)
        extract_send_partition.assert_called_once_with(
            kafka_producer, self.args, self.kwargs
        )
        tracer.start_as_current_span.assert_called_once_with(
            expected_span_name, kind=SpanKind.PRODUCER
        )

        span = tracer.start_as_current_span().__enter__.return_value
        enrich_span.assert_called_once_with(
            span,
            extract_bootstrap_servers.return_value,
            self.topic_name,
            extract_send_partition.return_value,
        )

        set_span_in_context.assert_called_once_with(span)
        context = set_span_in_context.return_value
        inject.assert_called_once_with(
            self.headers, context=context, setter=_kafka_setter
        )

        produce_hook.assert_called_once_with(span, self.args, self.kwargs)

        original_send_callback.assert_called_once_with(
            *self.args, **self.kwargs
        )
        self.assertEqual(retval, original_send_callback.return_value)

    @mock.patch("opentelemetry.propagate.extract")
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils._create_consumer_span"
    )
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_consumer_group"
    )
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers"
    )
    def test_wrap_next(
        self,
        extract_bootstrap_servers: mock.MagicMock,
        extract_consumer_group: mock.MagicMock,
        _create_consumer_span: mock.MagicMock,
        extract: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.MagicMock()
        original_next_callback = mock.MagicMock()
        kafka_consumer = mock.MagicMock()

        wrapped_next = _wrap_next(tracer, consume_hook)
        record = wrapped_next(
            original_next_callback, kafka_consumer, self.args, self.kwargs
        )

        extract_bootstrap_servers.assert_called_once_with(kafka_consumer)
        bootstrap_servers = extract_bootstrap_servers.return_value

        extract_consumer_group.assert_called_once_with(kafka_consumer)
        consumer_group = extract_consumer_group.return_value

        original_next_callback.assert_called_once_with(
            *self.args, **self.kwargs
        )
        self.assertEqual(record, original_next_callback.return_value)

        extract.assert_called_once_with(record.headers, getter=_kafka_getter)
        context = extract.return_value

        _create_consumer_span.assert_called_once_with(
            tracer,
            consume_hook,
            record,
            context,
            bootstrap_servers,
            consumer_group,
            self.args,
            self.kwargs,
        )

    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.context.attach")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._enrich_span")
    @mock.patch("opentelemetry.context.detach")
    def test_create_consumer_span(
        self,
        detach: mock.MagicMock,
        enrich_span: mock.MagicMock,
        attach: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.MagicMock()
        bootstrap_servers = mock.MagicMock()
        extracted_context = mock.MagicMock()
        record = mock.MagicMock()
        consumer_group = "test-consumer-group"

        _create_consumer_span(
            tracer,
            consume_hook,
            record,
            extracted_context,
            bootstrap_servers,
            consumer_group,
            self.args,
            self.kwargs,
        )

        expected_span_name = _get_span_name("receive", record.topic)

        tracer.start_as_current_span.assert_called_once_with(
            expected_span_name,
            context=extracted_context,
            kind=SpanKind.CONSUMER,
        )
        span = tracer.start_as_current_span.return_value.__enter__()
        set_span_in_context.assert_called_once_with(span, extracted_context)
        attach.assert_called_once_with(set_span_in_context.return_value)

        enrich_span.assert_called_once_with(
            span, bootstrap_servers, record.topic, record.partition
        )
        span.set_attribute.assert_called_once_with(
            messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME,
            consumer_group,
        )
        consume_hook.assert_called_once_with(
            span, record, self.args, self.kwargs
        )
        detach.assert_called_once_with(attach.return_value)

    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor"
    )
    def test_kafka_properties_extractor(
        self,
        kafka_properties_extractor: mock.MagicMock,
    ):
        kafka_properties_extractor._serialize.return_value = None
        kafka_properties_extractor._partition.return_value = "partition"
        assert (
            KafkaPropertiesExtractor.extract_send_partition(
                kafka_properties_extractor, self.args, self.kwargs
            )
            == "partition"
        )
        kafka_properties_extractor._wait_on_metadata.side_effect = Exception(
            "mocked error"
        )
        assert (
            KafkaPropertiesExtractor.extract_send_partition(
                kafka_properties_extractor, self.args, self.kwargs
            )
            is None
        )

    def test_extract_consumer_group(self) -> None:
        consumer = SimpleNamespace(config={"group_id": "billing-service"})
        self.assertEqual(
            KafkaPropertiesExtractor.extract_consumer_group(consumer),
            "billing-service",
        )

        # group_id not configured (manual partition assignment)
        consumer = SimpleNamespace(config={})
        self.assertIsNone(
            KafkaPropertiesExtractor.extract_consumer_group(consumer)
        )

        # instance without a config attribute must not raise
        self.assertIsNone(
            KafkaPropertiesExtractor.extract_consumer_group(object())
        )

    def _finished_consumer_span(self, consumer_group):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer(__name__)
        record = SimpleNamespace(
            topic="test_topic", partition=0, headers=[]
        )

        _create_consumer_span(
            tracer,
            None,
            record,
            None,
            ["localhost:9092"],
            consumer_group,
            self.args,
            self.kwargs,
        )

        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        return spans[0]

    def test_consumer_group_attribute_recorded(self) -> None:
        span = self._finished_consumer_span("billing-service")
        key = messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME
        self.assertEqual(key, "messaging.consumer.group.name")
        self.assertEqual(span.attributes[key], "billing-service")
        self.assertIsInstance(span.attributes[key], str)

    def test_consumer_group_attribute_absent_when_none(self) -> None:
        span = self._finished_consumer_span(None)
        self.assertNotIn(
            messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME,
            span.attributes,
        )
