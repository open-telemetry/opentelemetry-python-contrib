# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=unnecessary-dunder-call

from unittest import TestCase, mock

from kafka.errors import KafkaTimeoutError

from opentelemetry import trace
from opentelemetry.instrumentation.kafka.utils import (
    KafkaPropertiesExtractor,
    _create_consumer_span,
    _get_span_name,
    _kafka_getter,
    _kafka_setter,
    _wrap_next,
    _wrap_send,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


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
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers"
    )
    def test_wrap_next(
        self,
        extract_bootstrap_servers: mock.MagicMock,
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

        _create_consumer_span(
            tracer,
            consume_hook,
            record,
            extracted_context,
            bootstrap_servers,
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


class TestWrapSendSpanLifetime(TestBase):
    """The producer span must stay active while the wrapped `send` runs.

    Otherwise a synchronous failure happens after the span has already ended
    and is never recorded on it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.topic_name = "test_topic"
        self.args = [self.topic_name]
        self.kwargs = {"partition": 0, "headers": []}
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.producer = mock.MagicMock()

    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition",
        return_value=0,
    )
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers",
        return_value=["localhost:9092"],
    )
    def test_send_runs_inside_the_producer_span(
        self,
        extract_bootstrap_servers: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
    ) -> None:
        captured_span_context = {}

        def original_send(*args, **kwargs):
            captured_span_context["value"] = (
                trace.get_current_span().get_span_context()
            )
            return "future"

        wrapped_send = _wrap_send(self.tracer, None)
        retval = wrapped_send(
            original_send, self.producer, self.args, self.kwargs
        )

        self.assertEqual(retval, "future")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            captured_span_context["value"].span_id, spans[0].context.span_id
        )

    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition",
        return_value=0,
    )
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers",
        return_value=["localhost:9092"],
    )
    def test_send_exception_is_recorded_and_reraised(
        self,
        extract_bootstrap_servers: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
    ) -> None:
        expected_exception = KafkaTimeoutError(
            "Failed to update metadata after 60.0 secs."
        )
        original_send = mock.MagicMock(side_effect=expected_exception)

        wrapped_send = _wrap_send(self.tracer, None)
        with self.assertRaises(KafkaTimeoutError) as raised:
            wrapped_send(original_send, self.producer, self.args, self.kwargs)

        self.assertIs(raised.exception, expected_exception)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

        self.assertEqual(len(span.events), 1)
        event = span.events[0]
        self.assertEqual(event.name, "exception")
        self.assertEqual(
            event.attributes["exception.type"],
            "kafka.errors.KafkaTimeoutError",
        )
