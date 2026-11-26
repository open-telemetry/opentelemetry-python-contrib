# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=unnecessary-dunder-call

from types import SimpleNamespace
from unittest import TestCase, mock

from kafka.producer.future import FutureProduceResult, FutureRecordMetadata

from opentelemetry.instrumentation._semconv import _StabilityMode
from opentelemetry.instrumentation.kafka.utils import (
    KafkaPropertiesExtractor,
    _bootstrap_servers_attributes,
    _create_consumer_span,
    _get_attributes,
    _get_span_name,
    _kafka_getter,
    _kafka_setter,
    _wrap_next,
    _wrap_send,
)
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.samplertestutil import CapturingSampler
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
    @mock.patch("opentelemetry.instrumentation.kafka.utils._get_attributes")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    def test_wrap_send_with_topic_as_arg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        get_attributes: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.wrap_send_helper(
            inject,
            set_span_in_context,
            get_attributes,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers")
    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_send_partition")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._get_attributes")
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    def test_wrap_send_with_topic_as_kwarg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        get_attributes: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.args = []
        self.kwargs["topic"] = self.topic_name
        self.wrap_send_helper(
            inject,
            set_span_in_context,
            get_attributes,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    def wrap_send_helper(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        get_attributes: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        produce_hook = mock.MagicMock()
        original_send_callback = mock.MagicMock()
        kafka_producer = mock.MagicMock()
        expected_span_name = _get_span_name("send", self.topic_name)

        wrapped_send = _wrap_send(tracer, produce_hook, _StabilityMode.DEFAULT)
        retval = wrapped_send(original_send_callback, kafka_producer, self.args, self.kwargs)

        extract_bootstrap_servers.assert_called_once_with(kafka_producer)
        # The partition is read back from the future returned by send(), not
        # estimated from the call arguments.
        extract_send_partition.assert_called_once_with(original_send_callback.return_value)
        tracer.start_as_current_span.assert_called_once_with(
            expected_span_name, kind=SpanKind.PRODUCER, attributes=get_attributes.return_value
        )

        span = tracer.start_as_current_span().__enter__.return_value
        get_attributes.assert_called_once_with(
            extract_bootstrap_servers.return_value,
            self.topic_name,
            messaging_attributes.MessagingOperationTypeValues.SEND,
            _StabilityMode.DEFAULT,
        )
        span.set_attribute.assert_called_once_with(
            SpanAttributes.MESSAGING_KAFKA_PARTITION, extract_send_partition.return_value
        )

        set_span_in_context.assert_called_once_with(span)
        context = set_span_in_context.return_value
        inject.assert_called_once_with(self.headers, context=context, setter=_kafka_setter)

        produce_hook.assert_called_once_with(span, self.args, self.kwargs)

        original_send_callback.assert_called_once_with(*self.args, **self.kwargs)
        self.assertEqual(retval, original_send_callback.return_value)

    @mock.patch("opentelemetry.propagate.extract")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._create_consumer_span")
    @mock.patch("opentelemetry.instrumentation.kafka.utils.KafkaPropertiesExtractor.extract_bootstrap_servers")
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

        wrapped_next = _wrap_next(tracer, consume_hook, _StabilityMode.DEFAULT)
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
            self.args,
            self.kwargs,
            _StabilityMode.DEFAULT,
        )

    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.context.attach")
    @mock.patch("opentelemetry.instrumentation.kafka.utils._get_attributes")
    @mock.patch("opentelemetry.context.detach")
    def test_create_consumer_span(
        self,
        detach: mock.MagicMock,
        get_attributes: mock.MagicMock,
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
            _StabilityMode.DEFAULT,
        )

        expected_span_name = _get_span_name("receive", record.topic)

        tracer.start_as_current_span.assert_called_once_with(
            expected_span_name,
            context=extracted_context,
            kind=SpanKind.CONSUMER,
            attributes=get_attributes.return_value,
        )
        span = tracer.start_as_current_span.return_value.__enter__()
        set_span_in_context.assert_called_once_with(span, extracted_context)
        attach.assert_called_once_with(set_span_in_context.return_value)

        get_attributes.assert_called_once_with(
            bootstrap_servers,
            record.topic,
            messaging_attributes.MessagingOperationTypeValues.RECEIVE,
            _StabilityMode.DEFAULT,
            record.partition,
        )
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

    def test_get_attributes_records_partition_when_present(self) -> None:
        attributes = _get_attributes(
            ["localhost:9092"],
            self.topic_name,
            messaging_attributes.MessagingOperationTypeValues.SEND,
            _StabilityMode.DEFAULT,
            2,
        )

        self.assertEqual(attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION], 2)
        self.assertIs(type(attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION]), int)

    def test_get_attributes_omits_partition_when_none(self) -> None:
        attributes = _get_attributes(
            ["localhost:9092"],
            self.topic_name,
            messaging_attributes.MessagingOperationTypeValues.SEND,
            _StabilityMode.DEFAULT,
            None,
        )

        self.assertNotIn(SpanAttributes.MESSAGING_KAFKA_PARTITION, attributes)

    def test_get_attributes_omits_partition_when_none_in_messaging_mode(self) -> None:
        attributes = _get_attributes(
            ["localhost:9092"],
            self.topic_name,
            messaging_attributes.MessagingOperationTypeValues.SEND,
            _StabilityMode.MESSAGING,
            None,
        )

        self.assertNotIn(messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID, attributes)

    def test_get_attributes_records_partition_as_a_string_in_messaging_mode(self) -> None:
        attributes = _get_attributes(
            ["localhost:9092"],
            self.topic_name,
            messaging_attributes.MessagingOperationTypeValues.SEND,
            _StabilityMode.MESSAGING,
            2,
        )

        self.assertEqual(attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID], "2")
        self.assertIs(type(attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID]), str)
        self.assertNotIn(SpanAttributes.MESSAGING_KAFKA_PARTITION, attributes)


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

        wrapped_send = _wrap_send(self.tracer, None, _StabilityMode.DEFAULT)

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

        wrapped_send = _wrap_send(self.tracer, None, _StabilityMode.DEFAULT)
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


class TestKafkaSampling(TestBase):
    def _configure_sampler(self, sampler: CapturingSampler) -> None:
        self.tracer_provider, self.memory_exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(self.tracer_provider.shutdown)
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.client = SimpleNamespace(config={"bootstrap_servers": ["localhost:9092"]})

    def test_send_attributes_passed_to_sampler(self) -> None:
        for partition in (0, 7, None):
            with self.subTest(partition=partition):
                sampler = CapturingSampler()
                self._configure_sampler(sampler)
                future = (
                    FutureRecordMetadata(FutureProduceResult(("topic-1", partition)), 0, None, None, -1, -1, -1)
                    if partition is not None
                    else mock.Mock(spec=[])
                )
                send = mock.Mock(return_value=future)
                produce_hook = mock.Mock()
                kwargs = {"partition": 0, "headers": []}

                result = _wrap_send(self.tracer, produce_hook, _StabilityMode.DEFAULT)(
                    send, self.client, ("topic-1",), kwargs
                )

                expected = {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    SpanAttributes.MESSAGING_DESTINATION: "topic-1",
                    SpanAttributes.MESSAGING_URL: '["localhost:9092"]',
                }
                self.assertIs(result, future)
                send.assert_called_once_with("topic-1", **kwargs)
                self.assertEqual(sampler.kind, SpanKind.PRODUCER)
                self.assertEqual(sampler.attributes, expected)
                for key, value in expected.items():
                    self.assertIs(type(sampler.attributes[key]), type(value))
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                if partition is not None:
                    expected[SpanAttributes.MESSAGING_KAFKA_PARTITION] = partition
                    self.assertIs(type(spans[0].attributes[SpanAttributes.MESSAGING_KAFKA_PARTITION]), int)
                self.assertEqual(spans[0].attributes, expected)
                produce_hook.assert_called_once()

    def test_consumer_attributes_passed_to_sampler(self) -> None:
        sampler = CapturingSampler()
        self._configure_sampler(sampler)
        record = SimpleNamespace(topic="topic-1", partition=0, headers=[])
        receive = mock.Mock(return_value=record)
        consume_hook = mock.Mock()

        result = _wrap_next(self.tracer, consume_hook, _StabilityMode.DEFAULT)(receive, self.client, (), {})

        expected = {
            messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
            SpanAttributes.MESSAGING_DESTINATION: "topic-1",
            SpanAttributes.MESSAGING_URL: '["localhost:9092"]',
            SpanAttributes.MESSAGING_KAFKA_PARTITION: 0,
        }
        self.assertIs(result, record)
        self.assertEqual(sampler.kind, SpanKind.CONSUMER)
        self.assertEqual(sampler.attributes, expected)
        for key, value in expected.items():
            self.assertIs(type(sampler.attributes[key]), type(value))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes, expected)
        consume_hook.assert_called_once()

    def test_attributes_control_sampling(self) -> None:
        for method in ("send", "receive"):
            for topic, expected_count in (("sample", 1), ("drop", 0)):
                with self.subTest(method=method, topic=topic):
                    sampler = CapturingSampler(required_attributes={SpanAttributes.MESSAGING_DESTINATION: "sample"})
                    self._configure_sampler(sampler)
                    if method == "send":
                        future = FutureRecordMetadata(FutureProduceResult((topic, 0)), 0, None, None, -1, -1, -1)
                        callback = mock.Mock(return_value=future)
                        result = _wrap_send(self.tracer, None, _StabilityMode.DEFAULT)(
                            callback, self.client, (topic,), {}
                        )
                        self.assertIs(result, future)
                    else:
                        record = SimpleNamespace(topic=topic, partition=0, headers=[])
                        callback = mock.Mock(return_value=record)
                        result = _wrap_next(self.tracer, None, _StabilityMode.DEFAULT)(callback, self.client, (), {})
                        self.assertIs(result, record)
                    callback.assert_called_once()
                    self.assertEqual(len(self.memory_exporter.get_finished_spans()), expected_count)

    def test_consumer_error_propagates(self) -> None:
        self._configure_sampler(CapturingSampler())
        error = ConnectionError("broker unavailable")
        receive = mock.Mock(side_effect=error)

        with self.assertRaises(ConnectionError) as raised:
            _wrap_next(self.tracer, None, _StabilityMode.DEFAULT)(receive, self.client, (), {})

        self.assertIs(raised.exception, error)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)


class TestBootstrapServersAttributes(TestCase):
    """``bootstrap_servers`` is a ``host:port`` entry, a comma-separated string
    of them, or a list of them, so ``server.address`` and ``server.port`` have
    to be parsed out of it rather than copied from it."""

    def test_list_entry_splits_into_host_and_port(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes(["kafka-1:9092", "kafka-2:9092"]),
            {
                server_attributes.SERVER_ADDRESS: "kafka-1",
                server_attributes.SERVER_PORT: 9092,
            },
        )

    def test_comma_separated_string_uses_the_first_entry(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes("kafka-1:9092,kafka-2:9092"),
            {
                server_attributes.SERVER_ADDRESS: "kafka-1",
                server_attributes.SERVER_PORT: 9092,
            },
        )

    def test_bare_host_omits_the_port(self) -> None:
        """``localhost`` is kafka-python's own default for ``bootstrap_servers``."""
        self.assertEqual(
            _bootstrap_servers_attributes("localhost"),
            {server_attributes.SERVER_ADDRESS: "localhost"},
        )

    def test_security_protocol_prefix_is_stripped(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes("SASL_SSL://broker:9093"),
            {
                server_attributes.SERVER_ADDRESS: "broker",
                server_attributes.SERVER_PORT: 9093,
            },
        )

    def test_bracketed_ipv6_literal_with_a_port(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes("[::1]:9092"),
            {
                server_attributes.SERVER_ADDRESS: "::1",
                server_attributes.SERVER_PORT: 9092,
            },
        )

    def test_bracketed_ipv6_literal_without_a_port(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes("[::1]"),
            {server_attributes.SERVER_ADDRESS: "::1"},
        )

    def test_bare_ipv6_literal_is_not_split_on_its_last_colon(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes("::1"),
            {server_attributes.SERVER_ADDRESS: "::1"},
        )

    def test_non_numeric_port_is_omitted_rather_than_emitted(self) -> None:
        self.assertEqual(
            _bootstrap_servers_attributes("broker:not-a-port"),
            {server_attributes.SERVER_ADDRESS: "broker"},
        )

    def test_empty_values_record_nothing(self) -> None:
        for bootstrap_servers in (None, "", [], [""], ","):
            with self.subTest(bootstrap_servers=bootstrap_servers):
                self.assertEqual(_bootstrap_servers_attributes(bootstrap_servers), {})
