from unittest import TestCase, mock

from opentelemetry.instrumentation.kafka.utils import (
    _get_span_name,
    _kafka_getter,
    _kafka_setter,
    _start_consume_span_with_extracted_context,
    _wrap_next,
    _wrap_send,
)
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
    def test_wrap_send(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ):
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


    @mock.patch("opentelemetry.trace.get_current_span")
    @mock.patch("opentelemetry.trace.use_span")
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils._start_consume_span_with_extracted_context"
    )
    @mock.patch("opentelemetry.instrumentation.kafka.utils._enrich_span")
    @mock.patch(
        "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers"
    )
    def test_wrap_next(
        self,
        extract_bootstrap_servers: mock.MagicMock,
        enrich_span: mock.MagicMock,
        start_consume_span_with_extracted_context: mock.MagicMock,
        use_span: mock.MagicMock,
        get_current_span: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.MagicMock()
        original_next_callback = mock.MagicMock()
        kafka_consumer = mock.MagicMock()

        wrapped_next = _wrap_next(tracer, context_manager, consume_hook)

        wrapped_next = _wrap_next(tracer, consume_hook)
        record = wrapped_next(
            original_next_callback, kafka_consumer, self.args, self.kwargs
        )

        extract_bootstrap_servers.assert_called_once_with(kafka_consumer)
        bootstrap_servers = extract_bootstrap_servers.return_value

        get_current_span.assert_called_once()
        current_span = get_current_span.return_value
        current_span.end.assert_called_once()

        original_next_callback.assert_called_once_with(
            *self.args, **self.kwargs
        )
        self.assertEqual(record, original_next_callback.return_value)

        start_consume_span_with_extracted_context.assert_called_once_with(
            tracer, record.headers, record.topic
        )
        span = start_consume_span_with_extracted_context.return_value
        use_span.assert_called_once_with(span)
        enrich_span.assert_called_once_with(
            span, bootstrap_servers, record.topic, record.partition
        )
        consume_hook.assert_called_once_with(span, self.args, self.kwargs)


    @mock.patch("opentelemetry.context.attach")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.extract")
    def test_start_consume_span_with_extracted_context(
        self,
        extract: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        attach: mock.MagicMock,
    ):
        tracer = mock.MagicMock()
        kafka_consumer = mock.MagicMock()
        expected_span_name = _get_span_name("receive", self.topic_name)

        _start_consume_span_with_extracted_context(
            tracer,
            kafka_consumer,
            self.headers,
            self.topic_name,
        )

        extract.assert_called_once_with(self.headers, _kafka_getter)
        context = extract.return_value
        tracer.start_span.assert_called_once_with(
            expected_span_name, context=context, kind=SpanKind.CONSUMER
        )
        span = tracer.start_span.return_value
        set_span_in_context.assert_called_once_with(span, context)
        new_context = set_span_in_context.return_value
        attach.assert_called_once_with(new_context)
