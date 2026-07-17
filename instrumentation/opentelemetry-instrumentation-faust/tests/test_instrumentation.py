# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any
from unittest import IsolatedAsyncioTestCase, TestCase, mock

import faust
from faust.types.tuples import TP, Message, RecordMetadata
from wrapt import BoundFunctionWrapper

from opentelemetry import trace
from opentelemetry.instrumentation.faust import (
    FaustInstrumentor,
    OpenTelemetrySensor,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import (
    SpanKind,
    StatusCode,
    format_span_id,
    format_trace_id,
)


def _make_app(name: str | None = None) -> faust.App:
    app = faust.App(
        name or f"test-app-{uuid.uuid4()}",
        broker="kafka://localhost:9092",
        store="memory://",
    )
    app.finalize()
    return app


def _get_sensor(app: faust.App) -> OpenTelemetrySensor | None:
    for sensor in app.sensors:
        if isinstance(sensor, OpenTelemetrySensor):
            return sensor
    return None


class TestFaustInstrumentor(TestCase):
    def tearDown(self) -> None:
        instrumentor = FaustInstrumentor()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()

    def test_instrument_api(self) -> None:
        instrumentation = FaustInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(faust.App.__init__, BoundFunctionWrapper))

        instrumentation.uninstrument()
        self.assertFalse(isinstance(faust.App.__init__, BoundFunctionWrapper))

    def test_instrument_adds_sensor_to_new_apps(self) -> None:
        instrumentation = FaustInstrumentor()

        instrumentation.instrument()
        app = _make_app()
        self.assertIsNotNone(_get_sensor(app))

        instrumentation.uninstrument()
        self.assertIsNone(_get_sensor(app))

    def test_apps_created_before_instrument_are_not_instrumented(
        self,
    ) -> None:
        app = _make_app()
        instrumentation = FaustInstrumentor()

        instrumentation.instrument()
        self.assertIsNone(_get_sensor(app))
        instrumentation.uninstrument()

    def test_instrument_app(self) -> None:
        app = _make_app()
        instrumentation = FaustInstrumentor()

        instrumentation.instrument_app(app)
        self.assertIsNotNone(_get_sensor(app))

        # instrumenting twice must not add a second sensor
        instrumentation.instrument_app(app)
        self.assertEqual(
            len(
                [
                    sensor
                    for sensor in app.sensors
                    if isinstance(sensor, OpenTelemetrySensor)
                ]
            ),
            1,
        )

        instrumentation.uninstrument_app(app)
        self.assertIsNone(_get_sensor(app))


class TestFaustInstrumentation(TestBase, IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        FaustInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self) -> None:
        FaustInstrumentor().uninstrument()
        super().tearDown()

    @staticmethod
    def _mock_producer(
        app: faust.App, exception: Exception | None = None
    ) -> mock.Mock:
        producer = mock.Mock()
        producer.app = app

        async def _send(
            topic: str, *args: Any, **kwargs: Any
        ) -> asyncio.Future:
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            if exception is not None:
                fut.set_exception(exception)
            else:
                fut.set_result(
                    RecordMetadata(
                        topic=topic,
                        partition=0,
                        topic_partition=TP(topic, 0),
                        offset=1,
                        timestamp=None,
                        timestamp_type=None,
                    )
                )
            return fut

        producer.send = mock.Mock(side_effect=_send)
        return producer

    @staticmethod
    def _message_factory(
        offset: int, headers: list[tuple[str, bytes]] | None = None
    ) -> Message:
        return Message(
            topic="test-topic",
            partition=1,
            offset=offset,
            timestamp=time.time(),
            timestamp_type=0,
            headers=headers,
            key=b"test-key",
            value=b"test-value",
            checksum=None,
            generation_id=0,
        )

    def _assert_common_attributes(
        self, span: ReadableSpan, app: faust.App
    ) -> None:
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_SYSTEM],
            messaging_attributes.MessagingSystemValues.KAFKA.value,
        )
        self.assertEqual(
            span.attributes[server_attributes.SERVER_ADDRESS],
            json.dumps([str(url) for url in app.conf.broker]),
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_CLIENT_ID],
            app.conf.broker_client_id,
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_DESTINATION_NAME],
            "test-topic",
        )

    async def test_send(self) -> None:
        app = _make_app()
        producer = self._mock_producer(app)
        topic = app.topic("test-topic")

        with mock.patch.object(
            app, "maybe_start_producer", mock.AsyncMock(return_value=producer)
        ):
            await topic.send(key=b"test-key", value=b"test-value")
            # let the message-published callback run
            await asyncio.sleep(0)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "test-topic send")
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertIs(span.status.status_code, StatusCode.UNSET)
        self._assert_common_attributes(span, app)
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_OPERATION_NAME],
            "send",
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_OPERATION_TYPE],
            messaging_attributes.MessagingOperationTypeValues.PUBLISH.value,
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY],
            "test-key",
        )
        self.assertNotIn(
            messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID,
            span.attributes,
        )

        # span context must have been injected into the message headers
        producer.send.assert_called_once()
        headers = producer.send.call_args.kwargs["headers"]
        version, trace_id, span_id, flags = (
            headers["traceparent"].decode().split("-")
        )
        self.assertEqual(version, "00")
        self.assertEqual(trace_id, format_trace_id(span.context.trace_id))
        self.assertEqual(span_id, format_span_id(span.context.span_id))
        self.assertTrue(int(flags, 16) & 0x01)

    async def test_send_partition_attribute(self) -> None:
        app = _make_app()
        producer = self._mock_producer(app)
        topic = app.topic("test-topic")

        with mock.patch.object(
            app, "maybe_start_producer", mock.AsyncMock(return_value=producer)
        ):
            await topic.send(key=b"test-key", value=b"test-value", partition=7)
            await asyncio.sleep(0)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].attributes[
                messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID
            ],
            "7",
        )

    async def test_send_error(self) -> None:
        app = _make_app()
        error = RuntimeError("send failed")
        producer = self._mock_producer(app, exception=error)
        topic = app.topic("test-topic")

        with mock.patch.object(
            app, "maybe_start_producer", mock.AsyncMock(return_value=producer)
        ):
            fut = await topic.send(key=b"test-key", value=b"test-value")
            await asyncio.sleep(0)
            with self.assertRaises(RuntimeError):
                await fut

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "test-topic send")
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")

    async def test_stream_processing(self) -> None:
        app = _make_app()
        app.flow_control.resume()
        channel = app.channel()
        stream = channel.stream()

        remote_trace_id = 0x6E0C63257DE34C926F9EFCD03927272E
        remote_span_id = 0x00F067AA0BA902B7
        traceparent = (
            f"00-{format_trace_id(remote_trace_id)}"
            f"-{format_span_id(remote_span_id)}-01"
        )
        await stream.channel.deliver(
            self._message_factory(
                42, headers=[("traceparent", traceparent.encode())]
            )
        )
        await stream.channel.deliver(self._message_factory(43))

        iterator = aiter(stream)
        try:
            value = await anext(iterator)
            self.assertEqual(value, b"test-value")
            # while the event is being processed, the consumer span
            # must be active in the current context
            current_span = trace.get_current_span()
            self.assertEqual(
                current_span.get_span_context().trace_id, remote_trace_id
            )
            # pulling the next event acks the first one and ends its span
            await anext(iterator)
        finally:
            await stream.stop()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "test-topic process")
        self.assertEqual(span.kind, SpanKind.CONSUMER)
        self.assertEqual(span.context.trace_id, remote_trace_id)
        self.assertIsNotNone(span.parent)
        self.assertEqual(span.parent.span_id, remote_span_id)
        self._assert_common_attributes(span, app)
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_OPERATION_NAME],
            "process",
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_OPERATION_TYPE],
            messaging_attributes.MessagingOperationTypeValues.PROCESS.value,
        )
        self.assertEqual(
            span.attributes[
                messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID
            ],
            "1",
        )
        self.assertEqual(
            span.attributes[
                messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME
            ],
            app.conf.id,
        )
        self.assertEqual(
            span.attributes[
                messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET
            ],
            42,
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_MESSAGE_ID],
            "test-topic.1.42",
        )
        self.assertEqual(
            span.attributes[messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY],
            "test-key",
        )

    async def test_send_from_stream_continues_trace(self) -> None:
        app = _make_app()
        app.flow_control.resume()
        producer = self._mock_producer(app)
        channel = app.channel()
        stream = channel.stream()
        topic = app.topic("test-topic")

        remote_trace_id = 0x6E0C63257DE34C926F9EFCD03927272E
        traceparent = (
            f"00-{format_trace_id(remote_trace_id)}"
            f"-{format_span_id(0x00F067AA0BA902B7)}-01"
        )
        await stream.channel.deliver(
            self._message_factory(
                42, headers=[("traceparent", traceparent.encode())]
            )
        )
        await stream.channel.deliver(self._message_factory(43))

        iterator = aiter(stream)
        try:
            await anext(iterator)
            with mock.patch.object(
                app,
                "maybe_start_producer",
                mock.AsyncMock(return_value=producer),
            ):
                # message sent while processing an event: the producer
                # span must be a child of the consumer span
                await topic.send(
                    key=b"test-key", value=b"test-value", force=True
                )
                await asyncio.sleep(0)
            await anext(iterator)
        finally:
            await stream.stop()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        send_span = next(
            span for span in spans if span.name == "test-topic send"
        )
        process_span = next(
            span for span in spans if span.name == "test-topic process"
        )
        self.assertEqual(send_span.context.trace_id, remote_trace_id)
        self.assertEqual(
            send_span.parent.span_id, process_span.context.span_id
        )

    async def test_hooks(self) -> None:
        FaustInstrumentor().uninstrument()
        produce_hook = mock.Mock()
        process_hook = mock.Mock()
        FaustInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            produce_hook=produce_hook,
            process_hook=process_hook,
        )

        app = _make_app()
        app.flow_control.resume()
        producer = self._mock_producer(app)
        topic = app.topic("test-topic")
        channel = app.channel()
        stream = channel.stream()

        with mock.patch.object(
            app, "maybe_start_producer", mock.AsyncMock(return_value=producer)
        ):
            await topic.send(key=b"test-key", value=b"test-value")
            await asyncio.sleep(0)
        produce_hook.assert_called_once()

        await stream.channel.deliver(self._message_factory(42))
        iterator = aiter(stream)
        try:
            await anext(iterator)
        finally:
            await stream.stop()
        process_hook.assert_called_once()

    async def test_uninstrumented_app_produces_no_spans(self) -> None:
        app = _make_app()
        FaustInstrumentor().uninstrument_app(app)
        app.flow_control.resume()
        producer = self._mock_producer(app)
        topic = app.topic("test-topic")
        channel = app.channel()
        stream = channel.stream()

        with mock.patch.object(
            app, "maybe_start_producer", mock.AsyncMock(return_value=producer)
        ):
            await topic.send(key=b"test-key", value=b"test-value")
            await asyncio.sleep(0)

        await stream.channel.deliver(self._message_factory(42))
        iterator = aiter(stream)
        try:
            await anext(iterator)
        finally:
            await stream.stop()

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)
