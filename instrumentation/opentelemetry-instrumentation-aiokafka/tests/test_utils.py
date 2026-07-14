# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=unnecessary-dunder-call
from __future__ import annotations

from unittest import IsolatedAsyncioTestCase, mock

import aiokafka

from opentelemetry.instrumentation.aiokafka import _patch_cluster_id_capture
from opentelemetry.instrumentation.aiokafka.utils import (
    _MESSAGING_CLUSTER_ID,
    AIOKafkaContextGetter,
    AIOKafkaContextSetter,
    _aiokafka_getter,
    _aiokafka_setter,
    _create_consumer_span,
    _extract_cluster_id_from_client,
    _extract_send_partition,
    _get_span_name,
    _wrap_getmany,
    _wrap_getone,
    _wrap_send,
)
from opentelemetry.trace import SpanKind


class TestUtils(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.topic_name = "test_topic"
        self.args = [self.topic_name]
        self.headers = []
        self.kwargs = {"partition": 0, "headers": self.headers}

    def test_context_setter(self) -> None:
        context_setter = AIOKafkaContextSetter()

        carrier_list = [("key1", b"val1")]
        context_setter.set(carrier_list, "key2", "val2")
        self.assertTrue(("key2", b"val2") in carrier_list)

    def test_context_getter(self) -> None:
        context_setter = AIOKafkaContextSetter()
        context_getter = AIOKafkaContextGetter()

        carrier_list = []
        context_setter.set(carrier_list, "key1", "val1")
        self.assertEqual(context_getter.get(carrier_list, "key1"), ["val1"])
        self.assertEqual(["key1"], context_getter.keys(carrier_list))

    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_bootstrap_servers"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_send_partition"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._enrich_send_span"
    )
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    async def test_wrap_send_with_topic_as_arg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        await self.wrap_send_helper(
            inject,
            set_span_in_context,
            enrich_span,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_bootstrap_servers"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_send_partition"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._enrich_send_span"
    )
    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.propagate.inject")
    async def test_wrap_send_with_topic_as_kwarg(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.AsyncMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        self.args = []
        self.kwargs["topic"] = self.topic_name
        await self.wrap_send_helper(
            inject,
            set_span_in_context,
            enrich_span,
            extract_send_partition,
            extract_bootstrap_servers,
        )

    async def wrap_send_helper(
        self,
        inject: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
        enrich_span: mock.MagicMock,
        extract_send_partition: mock.AsyncMock,
        extract_bootstrap_servers: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        produce_hook = mock.AsyncMock()
        original_send_callback = mock.AsyncMock()
        kafka_producer = mock.MagicMock()
        kafka_producer.client.cluster.cluster_id = None
        expected_span_name = _get_span_name("send", self.topic_name)

        wrapped_send = _wrap_send(tracer, produce_hook)
        retval = await wrapped_send(
            original_send_callback, kafka_producer, self.args, self.kwargs
        )

        extract_bootstrap_servers.assert_called_once_with(
            kafka_producer.client
        )
        extract_send_partition.assert_awaited_once_with(
            kafka_producer, self.args, self.kwargs
        )
        tracer.start_as_current_span.assert_called_once_with(
            expected_span_name, kind=SpanKind.PRODUCER
        )

        span = tracer.start_as_current_span().__enter__.return_value
        enrich_span.assert_called_once_with(
            span,
            bootstrap_servers=extract_bootstrap_servers.return_value,
            client_id=kafka_producer.client._client_id,
            topic=self.topic_name,
            partition=extract_send_partition.return_value,
            key=None,
            cluster_id=None,
        )

        set_span_in_context.assert_called_once_with(span)
        context = set_span_in_context.return_value
        inject.assert_called_once_with(
            self.headers, context=context, setter=_aiokafka_setter
        )

        produce_hook.assert_awaited_once_with(span, self.args, self.kwargs)

        original_send_callback.assert_awaited_once_with(
            *self.args, **self.kwargs
        )
        self.assertEqual(retval, original_send_callback.return_value)

    @mock.patch("opentelemetry.propagate.extract")
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._create_consumer_span"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_bootstrap_servers"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_client_id"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_consumer_group"
    )
    async def test_wrap_getone(
        self,
        extract_consumer_group: mock.MagicMock,
        extract_client_id: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
        _create_consumer_span: mock.MagicMock,
        extract: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.AsyncMock()
        original_getone_callback = mock.AsyncMock()
        kafka_consumer = mock.MagicMock()
        kafka_consumer._client.cluster.cluster_id = None

        wrapped_getone = _wrap_getone(tracer, consume_hook)
        record = await wrapped_getone(
            original_getone_callback, kafka_consumer, self.args, self.kwargs
        )

        extract_bootstrap_servers.assert_called_once_with(
            kafka_consumer._client
        )
        bootstrap_servers = extract_bootstrap_servers.return_value

        extract_client_id.assert_called_once_with(kafka_consumer._client)
        client_id = extract_client_id.return_value

        extract_consumer_group.assert_called_once_with(kafka_consumer)
        consumer_group = extract_consumer_group.return_value

        original_getone_callback.assert_awaited_once_with(
            *self.args, **self.kwargs
        )
        self.assertEqual(record, original_getone_callback.return_value)

        extract.assert_called_once_with(
            record.headers, getter=_aiokafka_getter
        )
        context = extract.return_value

        _create_consumer_span.assert_called_once_with(
            tracer,
            consume_hook,
            record,
            context,
            bootstrap_servers,
            client_id,
            consumer_group,
            None,
            self.args,
            self.kwargs,
        )

    @mock.patch("opentelemetry.propagate.extract")
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._create_consumer_span"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._enrich_getmany_topic_span"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._enrich_getmany_poll_span"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_bootstrap_servers"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_client_id"
    )
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._extract_consumer_group"
    )
    # pylint: disable=too-many-locals
    async def test_wrap_getmany(
        self,
        extract_consumer_group: mock.MagicMock,
        extract_client_id: mock.MagicMock,
        extract_bootstrap_servers: mock.MagicMock,
        _enrich_getmany_poll_span: mock.MagicMock,
        _enrich_getmany_topic_span: mock.MagicMock,
        _create_consumer_span: mock.AsyncMock,
        extract: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.AsyncMock()
        record_mock = mock.MagicMock()
        original_getmany_callback = mock.AsyncMock(
            return_value={
                aiokafka.TopicPartition(topic="topic_1", partition=0): [
                    record_mock
                ]
            }
        )
        kafka_consumer = mock.MagicMock()
        kafka_consumer._client.cluster.cluster_id = None
        _create_consumer_span.return_value = mock.MagicMock()

        wrapped_getmany = _wrap_getmany(tracer, consume_hook)
        records = await wrapped_getmany(
            original_getmany_callback, kafka_consumer, self.args, self.kwargs
        )

        extract_bootstrap_servers.assert_called_once_with(
            kafka_consumer._client
        )
        bootstrap_servers = extract_bootstrap_servers.return_value

        extract_client_id.assert_called_once_with(kafka_consumer._client)
        client_id = extract_client_id.return_value

        extract_consumer_group.assert_called_once_with(kafka_consumer)
        consumer_group = extract_consumer_group.return_value

        original_getmany_callback.assert_awaited_once_with(
            *self.args, **self.kwargs
        )
        self.assertEqual(records, original_getmany_callback.return_value)

        extract.assert_called_once_with(
            record_mock.headers, getter=_aiokafka_getter
        )
        context = extract.return_value

        _create_consumer_span.assert_called_once_with(
            tracer,
            consume_hook,
            record_mock,
            context,
            bootstrap_servers,
            client_id,
            consumer_group,
            None,
            self.args,
            self.kwargs,
        )

    @mock.patch("opentelemetry.trace.set_span_in_context")
    @mock.patch("opentelemetry.context.attach")
    @mock.patch(
        "opentelemetry.instrumentation.aiokafka.utils._enrich_getone_span"
    )
    @mock.patch("opentelemetry.context.detach")
    async def test_create_consumer_span(
        self,
        detach: mock.MagicMock,
        enrich_span: mock.MagicMock,
        attach: mock.MagicMock,
        set_span_in_context: mock.MagicMock,
    ) -> None:
        tracer = mock.MagicMock()
        consume_hook = mock.AsyncMock()
        bootstrap_servers = mock.MagicMock()
        extracted_context = mock.MagicMock()
        record = mock.MagicMock()
        client_id = mock.MagicMock()
        consumer_group = mock.MagicMock()

        await _create_consumer_span(
            tracer,
            consume_hook,
            record,
            extracted_context,
            bootstrap_servers,
            client_id,
            consumer_group,
            None,
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
            span,
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            consumer_group=consumer_group,
            topic=record.topic,
            partition=record.partition,
            key=str(record.key),
            offset=record.offset,
            cluster_id=None,
        )
        consume_hook.assert_awaited_once_with(
            span, record, self.args, self.kwargs
        )
        detach.assert_called_once_with(attach.return_value)

    async def test_cluster_id_attribute_set_on_send_span(self) -> None:
        """Cluster ID is added to producer span when client metadata is available."""
        tracer = mock.MagicMock()
        span = mock.MagicMock()
        span.is_recording.return_value = True
        tracer.start_as_current_span.return_value.__enter__ = mock.Mock(
            return_value=span
        )
        tracer.start_as_current_span.return_value.__exit__ = mock.Mock(
            return_value=False
        )

        producer = mock.MagicMock()
        producer.client._bootstrap_servers = "broker1:9092,broker2:9092"
        producer.client._client_id = "test-client"
        producer.client._wait_on_metadata = mock.AsyncMock()
        producer.client.cluster.cluster_id = "test-cluster-uuid"
        producer._key_serializer = None
        producer._value_serializer = None
        producer._partition.return_value = 0

        wrapped_send = _wrap_send(tracer, None)
        await wrapped_send(mock.AsyncMock(), producer, [self.topic_name], {})

        set_attribute_calls = {
            call.args[0]: call.args[1]
            for call in span.set_attribute.call_args_list
        }
        self.assertEqual(
            set_attribute_calls.get(_MESSAGING_CLUSTER_ID),
            "test-cluster-uuid",
        )

    async def test_cluster_id_attribute_absent_when_not_resolved(self) -> None:
        """No cluster ID attribute is set when client metadata is not yet available."""
        tracer = mock.MagicMock()
        span = mock.MagicMock()
        span.is_recording.return_value = True
        tracer.start_as_current_span.return_value.__enter__ = mock.Mock(
            return_value=span
        )
        tracer.start_as_current_span.return_value.__exit__ = mock.Mock(
            return_value=False
        )

        producer = mock.MagicMock()
        producer.client._bootstrap_servers = "unknown-broker:9092"
        producer.client._client_id = "test-client"
        producer.client._wait_on_metadata = mock.AsyncMock()
        producer.client.cluster.cluster_id = None
        producer._key_serializer = None
        producer._value_serializer = None
        producer._partition.return_value = 0

        wrapped_send = _wrap_send(tracer, None)
        await wrapped_send(mock.AsyncMock(), producer, [self.topic_name], {})

        attribute_keys = [
            call.args[0] for call in span.set_attribute.call_args_list
        ]
        self.assertNotIn(_MESSAGING_CLUSTER_ID, attribute_keys)

    def test_patch_cluster_id_capture_sets_cluster_id_from_metadata(
        self,
    ) -> None:
        """_patch_cluster_id_capture intercepts update_metadata and sets cluster_id."""
        cluster = mock.MagicMock(spec=[])
        cluster.cluster_id = None
        update_calls: list[object] = []

        def original_update(metadata: object) -> None:
            update_calls.append(metadata)

        cluster.update_metadata = original_update
        client = mock.MagicMock()
        client.cluster = cluster

        _patch_cluster_id_capture(client)

        metadata = mock.MagicMock()
        metadata.cluster_id = "test-cluster-uuid"
        cluster.update_metadata(metadata)

        self.assertEqual(cluster.cluster_id, "test-cluster-uuid")
        self.assertEqual(update_calls, [metadata])

    def test_patch_cluster_id_capture_is_idempotent(self) -> None:
        """Calling _patch_cluster_id_capture twice does not double-wrap."""
        cluster = mock.MagicMock(spec=[])
        update_calls: list[object] = []
        cluster.update_metadata = update_calls.append
        client = mock.MagicMock()
        client.cluster = cluster

        _patch_cluster_id_capture(client)
        _patch_cluster_id_capture(client)

        metadata = mock.MagicMock()
        metadata.cluster_id = "id-1"
        cluster.update_metadata(metadata)

        # original called exactly once despite two patch calls
        self.assertEqual(len(update_calls), 1)

    @staticmethod
    def test_patch_cluster_id_capture_ignores_none_cluster() -> None:
        """_patch_cluster_id_capture is a no-op when client has no cluster."""
        client = mock.MagicMock(spec=[])  # no attributes
        _patch_cluster_id_capture(client)  # must not raise

    def test_extract_cluster_id_from_client_returns_cluster_id(self) -> None:
        """Returns cluster ID from client.cluster.cluster_id when available."""
        client = mock.MagicMock()
        client.cluster.cluster_id = "abc-uuid-1234"
        self.assertEqual(
            _extract_cluster_id_from_client(client), "abc-uuid-1234"
        )

    def test_extract_cluster_id_from_client_returns_none_when_cluster_id_none(
        self,
    ) -> None:
        """Returns None when cluster_id is None (metadata not yet received)."""
        client = mock.MagicMock()
        client.cluster.cluster_id = None
        self.assertIsNone(_extract_cluster_id_from_client(client))

    def test_extract_cluster_id_from_client_returns_none_when_no_cluster_attr(
        self,
    ) -> None:
        """Returns None when client has no cluster attribute."""
        client = mock.MagicMock(spec=[])  # no attributes
        self.assertIsNone(_extract_cluster_id_from_client(client))

    def test_extract_cluster_id_from_client_returns_none_on_exception(
        self,
    ) -> None:
        """Returns None if attribute access raises unexpectedly."""
        client = mock.MagicMock()
        type(client).cluster = mock.PropertyMock(
            side_effect=RuntimeError("boom")
        )
        self.assertIsNone(_extract_cluster_id_from_client(client))

    async def test_kafka_properties_extractor(self):
        aiokafka_instance_mock = mock.Mock()
        aiokafka_instance_mock._key_serializer = None
        aiokafka_instance_mock._value_serializer = None
        aiokafka_instance_mock._partition.return_value = "partition"
        aiokafka_instance_mock.client._wait_on_metadata = mock.AsyncMock()
        assert (
            await _extract_send_partition(
                aiokafka_instance_mock, self.args, self.kwargs
            )
            == "partition"
        )
        aiokafka_instance_mock.client._wait_on_metadata.side_effect = (
            Exception("mocked error")
        )
        assert (
            await _extract_send_partition(
                aiokafka_instance_mock, self.args, self.kwargs
            )
            is None
        )
