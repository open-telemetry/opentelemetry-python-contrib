# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=unnecessary-dunder-call

from unittest import TestCase, mock

from kafka.producer.future import FutureProduceResult, FutureRecordMetadata

from opentelemetry.instrumentation.kafka.utils import (
    KafkaPropertiesExtractor,
    _create_consumer_span,
    _enrich_span,
    _extract_cluster_id,
    _get_span_name,
    _kafka_getter,
    _kafka_setter,
    _patch_cluster_id_capture,
    _wrap_next,
    _wrap_send,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


class TestUtils(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.topic_name = "test_topic"
        self.args = [self.topic_name]
        self.headers = []
        self.kwargs = {"partition": 0, "headers": self.headers}

    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers")
    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._extract_cluster_id")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._enrich_span")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    def test_wrap_send_with_topic_as_arg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_cluster_id: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.wrap_send_helper(
            inject,
            set_span_in_context,
            enrich_span,
            extract_cluster_id,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers")
    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._extract_cluster_id")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._enrich_span")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    def test_wrap_send_with_topic_as_kwarg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_cluster_id: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.args = []
        self.kwargs["topic"] = self.topic_name
        self.wrap_send_helper(
            inject,
            set_span_in_context,
            enrich_span,
            extract_cluster_id,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    def wrap_send_helper(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_cluster_id: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        produce_hook = mock.MagicMock()
        original_send_callback = mock.MagicMock()
        kafka_producer = mock.MagicMock()
        expected_span_name = _get_span_name("send", self.topic_name)

        wrapped_send = _wrap_send(tracer, produce_hook)
        retval = wrapped_send(original_send_callback, kafka_producer, self.args, self.kwargs)

        extract_bootstrap_servers.assert_called_once_with(kafka_producer)
        # The partition is read back from the future returned by send(), not
        # estimated from the call arguments.
        extract_send_partition.assert_called_once_with(original_send_callback.return_value)
        tracer.start_as_current_span.assert_called_once_with(expected_span_name, kind=SpanKind.PRODUCER)

        span = tracer.start_as_current_span().__enter__.return_value
        enrich_span.assert_called_once_with(
            span,
            extract_bootstrap_servers.return_value,
            self.topic_name,
            extract_send_partition.return_value,
            extract_cluster_id.return_value,
        )

        set_span_in_context.assert_called_once_with(span)
        context = set_span_in_context.return_value
        inject.assert_called_once_with(self.headers, context=context, setter=_kafka_setter)

        produce_hook.assert_called_once_with(span, self.args, self.kwargs)

        original_send_callback.assert_called_once_with(*self.args, **self.kwargs)
        self.assertEqual(retval, original_send_callback.return_value)

    @mock.patch("opentelemetry.instrumentation.kafka.utils._extract_cluster_id")
    @mock.patch("opentelemetry.propagate.extract")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._create_consumer_span")
    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers")
    def test_wrap_next(
        self,
        extract_bootstrap_servers: mock.MagicMock,
        _create_consumer_span: mock.MagicMock,
        extract: mock.MagicMock,
        extract_cluster_id: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.MagicMock()
        original_next_callback = mock.MagicMock()
        kafka_consumer = mock.MagicMock()

        wrapped_next = _wrap_next(tracer, consume_hook)
        record = wrapped_next(original_next_callback, kafka_consumer, self.args, self.kwargs)

        extract_bootstrap_servers.assert_called_once_with(kafka_consumer)
        bootstrap_servers = extract_bootstrap_servers.return_value

        original_next_callback.assert_called_once_with(*self.args, **self.kwargs)
        self.assertEqual(record, original_next_callback.return_value)

        extract.assert_called_once_with(record.headers, getter=_kafka_getter)
        context = extract.return_value

        _create_consumer_span.assert_called_once_with(
            tracer,
            consume_hook,
            record,
            context,
            bootstrap_servers,
            extract_cluster_id.return_value,
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
        cluster_id = mock.MagicMock()

        _create_consumer_span(
            tracer,
            consume_hook,
            record,
            extracted_context,
            bootstrap_servers,
            cluster_id,
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

        enrich_span.assert_called_once_with(span, bootstrap_servers, record.topic, record.partition, cluster_id)
        consume_hook.assert_called_once_with(span, record, self.args, self.kwargs)
        detach.assert_called_once_with(attach.return_value)

    def test_extract_send_partition_reads_actual_partition_from_future(self):
        """The partition is read back from the future returned by ``send()``,
        which reflects where the message was actually routed.

        Regression test for
        https://github.com/open-telemetry/opentelemetry-python-contrib/issues/4625
        """
        future = mock.MagicMock()
        future._produce_future.topic_partition = ("test_topic", 7)

        partition = KafkaPropertiesExtractor.extract_send_partition(future)

        self.assertEqual(partition, 7)

    def test_extract_send_partition_zero(self):
        """Partition ``0`` is falsy but valid and must not be dropped."""
        future = mock.MagicMock()
        future._produce_future.topic_partition = ("test_topic", 0)

        partition = KafkaPropertiesExtractor.extract_send_partition(future)

        self.assertEqual(partition, 0)

    def test_extract_send_partition_matches_real_kafka_future(self):
        """Guards against kafka-python changing the internal attribute the
        extractor relies on."""
        produce_future = FutureProduceResult(("test_topic", 4))
        future = FutureRecordMetadata(produce_future, 0, None, None, -1, -1, -1)

        partition = KafkaPropertiesExtractor.extract_send_partition(future)

        self.assertEqual(partition, 4)

    def test_extract_send_partition_returns_none_when_unavailable(self):
        """If the future does not expose the expected internals, the attribute
        is omitted rather than raising."""

        class _NoInternals:
            pass

        partition = KafkaPropertiesExtractor.extract_send_partition(_NoInternals())

        self.assertIsNone(partition)

    def test_enrich_span_records_partition_when_present(self):
        span = mock.MagicMock()
        span.is_recording.return_value = True

        _enrich_span(span, ["localhost:9092"], self.topic_name, 2)

        span.set_attribute.assert_any_call(SpanAttributes.MESSAGING_KAFKA_PARTITION, 2)

    def test_enrich_span_omits_partition_when_none(self):
        span = mock.MagicMock()
        span.is_recording.return_value = True

        _enrich_span(span, ["localhost:9092"], self.topic_name, None)

        recorded_attributes = {call.args[0] for call in span.set_attribute.call_args_list}
        self.assertNotIn(SpanAttributes.MESSAGING_KAFKA_PARTITION, recorded_attributes)

    def test_extract_cluster_id_from_producer_metadata(self) -> None:
        producer = mock.MagicMock()
        producer._metadata.cluster_id = "test-cluster-id"
        self.assertEqual(_extract_cluster_id(producer), "test-cluster-id")

    def test_extract_cluster_id_from_consumer_client(self) -> None:
        consumer = mock.MagicMock(spec=["_client"])
        consumer._client.cluster.cluster_id = "test-cluster-id"
        self.assertEqual(_extract_cluster_id(consumer), "test-cluster-id")

    def test_extract_cluster_id_absent_returns_none(self) -> None:
        instance = mock.MagicMock(spec=[])
        self.assertIsNone(_extract_cluster_id(instance))

    def test_patch_cluster_id_capture_captures_and_is_idempotent(
        self,
    ) -> None:
        class FakeCluster:
            def __init__(self) -> None:
                self.update_calls = 0

            def update_metadata(self, metadata) -> None:
                self.update_calls += 1

        class FakeMetadataResponse:
            cluster_id = "test-cluster-id"

        cluster = FakeCluster()
        instance = mock.MagicMock()
        instance._metadata = cluster

        _patch_cluster_id_capture(instance)
        # Second call must not double-wrap update_metadata.
        _patch_cluster_id_capture(instance)

        cluster.update_metadata(FakeMetadataResponse())

        self.assertEqual(cluster.update_calls, 1)
        self.assertEqual(_extract_cluster_id(instance), "test-cluster-id")


@mock.patch(
    "opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition",
    return_value=0,
)
class TestWrapSendSpanLifetime(TestBase):
    """The producer span must stay open while the wrapped ``send`` runs, so
    that errors raised by ``send()`` are recorded on the span."""

    def setUp(self) -> None:
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.topic_name = "test_topic"
        self.args = [self.topic_name]
        self.kwargs = {"partition": 0, "headers": []}
        self.producer = mock.MagicMock()
        self.producer.config = {"bootstrap_servers": ["localhost:9092"]}

    def test_wrap_send_records_exception_raised_by_send(self, _extract_send_partition: mock.MagicMock) -> None:
        error = ConnectionError("broker unavailable")

        def failing_send(*args, **kwargs):
            raise error

        wrapped_send = _wrap_send(self.tracer, None)

        with self.assertRaises(ConnectionError) as raised:
            wrapped_send(failing_send, self.producer, self.args, self.kwargs)

        self.assertIs(raised.exception, error)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, _get_span_name("send", self.topic_name))
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")
        self.assertEqual(span.events[0].attributes["exception.type"], "ConnectionError")

    def test_wrap_send_leaves_successful_send_unchanged(self, _extract_send_partition: mock.MagicMock) -> None:
        original_send = mock.MagicMock()

        wrapped_send = _wrap_send(self.tracer, None)
        retval = wrapped_send(original_send, self.producer, self.args, self.kwargs)

        original_send.assert_called_once_with(*self.args, **self.kwargs)
        self.assertEqual(retval, original_send.return_value)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, _get_span_name("send", self.topic_name))
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertIs(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(len(span.events), 0)
