import contextlib
from typing import Any, Callable, Dict, NamedTuple, Optional, Tuple

import botocore.session
from moto import mock_sns, mock_sqs

from opentelemetry.context import attach, detach
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.botocore.extensions.sqs import (
    sqs_processing_span,
    wrap_sqs_processing,
)
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    MessagingOperationValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.span import (
    NonRecordingSpan,
    Span,
    SpanContext,
    TraceFlags,
)

_default_queue_name = "test-queue"
_default_topic_name = "test-topic"


class SqsQueue(NamedTuple):
    url: str
    name: str


class SnsTopic(NamedTuple):
    arn: str
    name: str


@contextlib.contextmanager
def _active_span(trace_id: int = 37, span_id: int = 73):
    sampled = TraceFlags(TraceFlags.SAMPLED)
    span = NonRecordingSpan(
        SpanContext(trace_id, span_id, is_remote=False, trace_flags=sampled)
    )
    token = attach(set_span_in_context(span))
    try:
        yield span
    finally:
        detach(token)


class TestSqsExtension(TestBase):
    def setUp(self):
        super().setUp()
        BotocoreInstrumentor().instrument()

        session = botocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"
        self.client = session.create_client("sqs", region_name=self.region)
        self.sns_client = session.create_client("sns", region_name=self.region)

    def tearDown(self):
        super().tearDown()
        BotocoreInstrumentor().uninstrument()

    def _create_queue(self, queue_name: str = _default_queue_name) -> SqsQueue:
        result = self.client.create_queue(QueueName=queue_name)

        # ignore create queue span
        self.memory_exporter.clear()

        return SqsQueue(result["QueueUrl"], queue_name)

    def _create_sns_to_sqs(
        self,
        queue_name: str = _default_queue_name,
        topic_name: str = _default_topic_name,
        raw_msg_delivery: bool = False,
    ) -> Tuple[SqsQueue, SnsTopic]:
        topic = self.sns_client.create_topic(Name=topic_name)
        queue = self.client.create_queue(QueueName=queue_name)
        queue_arn = self.client.get_queue_attributes(
            QueueUrl=queue["QueueUrl"], AttributeNames=["QueueArn"]
        )

        self.sns_client.subscribe(
            TopicArn=topic["TopicArn"],
            Protocol="sqs",
            Endpoint=queue_arn["Attributes"]["QueueArn"],
            Attributes={
                "RawMessageDelivery": "true" if raw_msg_delivery else "false"
            },
        )

        self.memory_exporter.clear()
        return (
            SqsQueue(queue["QueueUrl"], queue_name),
            SnsTopic(topic["TopicArn"], topic_name),
        )

    def _assert_span(self, name: str, span_kind=SpanKind.PRODUCER) -> Span:
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        span = spans[0]

        self.assertEqual(span_kind, span.kind)
        self.assertEqual(name, span.name)
        self.assertEqual(
            "aws.sqs", span.attributes[SpanAttributes.MESSAGING_SYSTEM]
        )

        return span

    def _assert_common_span_attrs(self, span: Span, queue: SqsQueue):
        self.assertEqual(
            queue.url, span.attributes[SpanAttributes.MESSAGING_URL]
        )
        self.assertEqual(
            queue.name, span.attributes[SpanAttributes.MESSAGING_DESTINATION]
        )
        self.assertEqual(
            MessagingDestinationKindValues.QUEUE.value,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_KIND],
        )

    def _assert_send_span(
        self,
        queue: SqsQueue,
        message: Optional[Dict[str, Any]] = None,
    ) -> Span:
        span = self._assert_span(f"{queue.name} send", SpanKind.PRODUCER)
        self._assert_common_span_attrs(span, queue)
        if message:
            self.assertEqual(
                message["MessageId"],
                span.attributes[SpanAttributes.MESSAGING_MESSAGE_ID],
            )
        return span

    def _assert_receive_span(self, queue: SqsQueue) -> Span:
        span = self._assert_span(f"{queue.name} receive", SpanKind.CONSUMER)
        self._assert_common_span_attrs(span, queue)
        self.assertEqual(
            MessagingOperationValues.RECEIVE.value,
            span.attributes[SpanAttributes.MESSAGING_OPERATION],
        )
        return span

    def _assert_process_span(
        self, queue: SqsQueue, message: Dict[str, Any]
    ) -> Span:
        span = self._assert_span(f"{queue.name} process", SpanKind.CONSUMER)
        self._assert_common_span_attrs(span, queue)
        self.assertEqual(
            message["MessageId"],
            span.attributes[SpanAttributes.MESSAGING_MESSAGE_ID],
        )
        self.assertEqual(
            MessagingOperationValues.PROCESS.value,
            span.attributes[SpanAttributes.MESSAGING_OPERATION],
        )
        return span

    def _assert_link(self, span: Span, linked_span: Optional[Span]):
        if not linked_span:
            self.assertEqual(0, len(span.links))
            return

        self.assertEqual(1, len(span.links))
        link_ctx = span.links[0].context
        expected_ctx = linked_span.get_span_context()

        self.assertEqual(expected_ctx.trace_id, link_ctx.trace_id)
        self.assertEqual(expected_ctx.span_id, link_ctx.span_id)

    def _assert_injected_span(self, message_attrs: Dict[str, Any], span: Span):
        # traceparent: <ver>-<trace-id>-<span-id>-<flags>
        trace_parent = message_attrs["traceparent"]["StringValue"].split("-")
        span_context = span.get_span_context()

        self.assertEqual(span_context.trace_id, int(trace_parent[1], 16))
        self.assertEqual(span_context.span_id, int(trace_parent[2], 16))

    def _assert_parent(self, span: Span, parent_span: Span = None):
        if not parent_span:
            self.assertIsNone(span.parent)
            return

        parent_ctx = parent_span.get_span_context()
        self.assertEqual(parent_ctx.trace_id, span.parent.trace_id)
        self.assertEqual(parent_ctx.span_id, span.parent.span_id)

    @mock_sqs
    def test_sqs_messaging_send_message(self):
        queue = self._create_queue()

        response = self.client.send_message(
            QueueUrl=queue.url, MessageBody="content"
        )

        span = self._assert_send_span(queue, response)
        self.assertEqual(
            "SendMessage", span.attributes[SpanAttributes.RPC_METHOD]
        )

    @mock_sqs
    def test_send_message_injects_span(self):
        msg_attrs = {}
        queue = self._create_queue()
        self.client.send_message(
            QueueUrl=queue.url, MessageBody="msg", MessageAttributes=msg_attrs
        )

        span = self._assert_send_span(queue)
        self._assert_injected_span(msg_attrs, span)

    @mock_sqs
    def test_sqs_messaging_send_message_batch(self):
        queue = self._create_queue()

        self.client.send_message_batch(
            QueueUrl=queue.url,
            Entries=[
                {"Id": "1", "MessageBody": "content"},
                {"Id": "2", "MessageBody": "content2"},
            ],
        )

        span = self._assert_send_span(queue)
        self.assertEqual(
            "SendMessageBatch", span.attributes[SpanAttributes.RPC_METHOD]
        )

    @mock_sqs
    def test_send_message_batch_injects_span(self):
        msg_attrs1 = {}
        msg_attrs2 = {}
        queue = self._create_queue()
        self.client.send_message_batch(
            QueueUrl=queue.url,
            Entries=[
                {
                    "Id": "1",
                    "MessageBody": "Msg 1",
                    "MessageAttributes": msg_attrs1,
                },
                {
                    "Id": "2",
                    "MessageBody": "Msg 2",
                    "MessageAttributes": msg_attrs2,
                },
            ],
        )

        span = self._assert_send_span(queue)
        self._assert_injected_span(msg_attrs1, span)
        self._assert_injected_span(msg_attrs2, span)

    def _send_and_receive_message(
        self,
    ) -> Tuple[SqsQueue, Span, Span, Dict[str, Any]]:
        queue = self._create_queue()

        result = self.client.send_message(
            QueueUrl=queue.url, MessageBody="hello"
        )
        send_span = self._assert_send_span(queue, result)
        self.memory_exporter.clear()

        result = self.client.receive_message(QueueUrl=queue.url)
        receive_span = self._assert_receive_span(queue)
        self.memory_exporter.clear()

        self.assertEqual(1, len(result["Messages"]))

        return queue, send_span, receive_span, result

    @mock_sqs
    def test_sqs_messaging_receive_message(self):
        _, _, span, _ = self._send_and_receive_message()

        self.assertEqual(
            "ReceiveMessage", span.attributes[SpanAttributes.RPC_METHOD]
        )

    @mock_sqs
    def test_process_message_ctx_manager(self):
        queue, send_span, rcv_span, result = self._send_and_receive_message()

        with sqs_processing_span(result["Messages"][0]):
            pass

        span = self._assert_process_span(queue, result["Messages"][0])
        self._assert_parent(span, rcv_span)
        self._assert_link(span, send_span)

    @mock_sqs
    def test_process_message_ctx_manager_with_active_span(self):
        queue, send_span, rcv_span, result = self._send_and_receive_message()

        with _active_span():
            with sqs_processing_span(result["Messages"][0]):
                pass

        span = self._assert_process_span(queue, result["Messages"][0])
        self._assert_parent(span, rcv_span)
        self._assert_link(span, send_span)

    @mock_sqs
    def test_process_message_decorator(self):
        queue, send_span, rcv_span, result = self._send_and_receive_message()

        @wrap_sqs_processing
        def _process(_):
            pass

        _process(result["Messages"][0])
        span = self._assert_process_span(queue, result["Messages"][0])
        self._assert_parent(span, rcv_span)
        self._assert_link(span, send_span)

    @mock_sqs
    def test_process_message_decorator_with_active_span(self):
        queue, send_span, rcv_span, result = self._send_and_receive_message()

        @wrap_sqs_processing
        def _process(_):
            pass

        with _active_span():
            _process(result["Messages"][0])

        span = self._assert_process_span(queue, result["Messages"][0])
        self._assert_parent(span, rcv_span)
        self._assert_link(span, send_span)

    def test_process_message_ctx_manager_ignores_non_receive_msg(self):
        with sqs_processing_span({}):
            pass

        self.assertEqual(0, len(self.memory_exporter.get_finished_spans()))

    def test_process_message_decorator_ignores_non_receive_msg(self):
        @wrap_sqs_processing
        def process(_1, _msg, _2):
            pass

        process(1, {}, 2)

        self.assertEqual(0, len(self.memory_exporter.get_finished_spans()))

    @mock_sqs
    def test_receive_and_process_multiple_messages(self):
        queue = self._create_queue()
        self.client.send_message_batch(
            QueueUrl=queue.url,
            Entries=[
                {"Id": "1", "MessageBody": "msg1"},
                {"Id": "2", "MessageBody": "msg2"},
            ],
        )

        send_span = self._assert_send_span(queue)
        self.memory_exporter.clear()

        response = self.client.receive_message(QueueUrl=queue.url)
        self._assert_receive_span(queue)

        self.assertGreater(len(response["Messages"]), 0)
        for message in response["Messages"]:
            self.memory_exporter.clear()

            with sqs_processing_span(message):
                pass

            span = self._assert_process_span(queue, message)
            self._assert_link(span, send_span)

    @mock_sqs
    @mock_sns
    def _test_sns_to_sqs(
        self,
        raw_message_delivery: bool,
        processor: Callable[[Any], None] = None,
    ):
        queue, topic = self._create_sns_to_sqs(
            raw_msg_delivery=raw_message_delivery
        )

        # send message -> sns
        self.sns_client.publish(TopicArn=topic.arn, Message="Hello message")
        self.assertEqual(1, len(self.memory_exporter.get_finished_spans()))
        send_span = self.memory_exporter.get_finished_spans()[0]
        self.memory_exporter.clear()

        # sqs -> receive message
        result = self.client.receive_message(QueueUrl=queue.url)
        receive_span = self._assert_receive_span(queue)
        self.memory_exporter.clear()

        # process message
        message = result["Messages"][0]
        if processor:
            processor(message)
        else:
            with sqs_processing_span(
                message, extract_from_payload=not raw_message_delivery
            ):
                pass

        span = self._assert_process_span(queue, message)
        self._assert_parent(span, receive_span)
        self._assert_link(span, send_span)

    def test_sns_to_sqs_via_payload_delivery(self):
        self._test_sns_to_sqs(raw_message_delivery=False)

    def test_sns_to_sqs_raw_message_delivery(self):
        self._test_sns_to_sqs(raw_message_delivery=True)

    def test_sns_to_sqs_via_payload_delivery_decorator(self):
        @wrap_sqs_processing(extract_from_payload=True)
        def _process(_):
            pass

        self._test_sns_to_sqs(raw_message_delivery=False, processor=_process)

    @mock_sqs
    @mock_sns
    def test_sns_to_sqs_payload_delivery_no_extract(self):
        queue, topic = self._create_sns_to_sqs(raw_msg_delivery=False)

        self.sns_client.publish(TopicArn=topic.arn, Message="Hello message")
        self.memory_exporter.clear()

        result = self.client.receive_message(QueueUrl=queue.url)
        self._assert_receive_span(queue)
        self.memory_exporter.clear()

        # process message
        message = result["Messages"][0]
        with sqs_processing_span(message, extract_from_payload=False):
            pass

        span = self._assert_process_span(queue, message)
        self._assert_link(span, None)  # no links, not extracted form payload

    @mock_sqs
    def test_sqs_messaging_failed_operation(self):
        queue = SqsQueue("non-existing", "non-existing")
        with self.assertRaises(Exception):
            self.client.send_message(QueueUrl=queue.url, MessageBody="content")

        span = self._assert_send_span(queue)
        self.assertEqual(1, len(span.events))
        error_event = span.events[0]
        self.assertIn(SpanAttributes.EXCEPTION_MESSAGE, error_event.attributes)
        self.assertIn(SpanAttributes.EXCEPTION_TYPE, error_event.attributes)
