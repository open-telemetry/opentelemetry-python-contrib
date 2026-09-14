# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=no-name-in-module

from contextlib import contextmanager
from contextvars import copy_context
from typing import Any
from unittest import TestCase, mock

import boto3
from botocore.awsrequest import AWSResponse
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.boto3sqs import (
    Boto3SQSGetter,
    Boto3SQSInstrumentor,
    Boto3SQSSetter,
    _active_processing_span,
)
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    MessagingOperationValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, TraceFlags
from opentelemetry.trace.span import Span, format_span_id, format_trace_id


def _make_sqs_client(*, session=False):
    return (boto3.Session() if session else boto3).client(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
    )


def _make_sqs_resource(*, session=False):
    return (boto3.Session() if session else boto3).resource(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
    )


class TestBoto3SQSInstrumentor(TestCase):
    def _assert_instrumented(self, client):
        self.assertIsInstance(client.send_message, BoundFunctionWrapper)
        self.assertIsInstance(client.send_message_batch, BoundFunctionWrapper)
        self.assertIsInstance(client.receive_message, BoundFunctionWrapper)
        self.assertIsInstance(client.delete_message, BoundFunctionWrapper)
        self.assertIsInstance(client.delete_message_batch, BoundFunctionWrapper)

    def _assert_uninstrumented(self, client):
        self.assertNotIsInstance(client.send_message, BoundFunctionWrapper)
        self.assertNotIsInstance(client.send_message_batch, BoundFunctionWrapper)
        self.assertNotIsInstance(client.receive_message, BoundFunctionWrapper)
        self.assertNotIsInstance(client.delete_message, BoundFunctionWrapper)
        self.assertNotIsInstance(client.delete_message_batch, BoundFunctionWrapper)

    @staticmethod
    @contextmanager
    def _active_instrumentor():
        Boto3SQSInstrumentor().instrument()
        try:
            yield
        finally:
            Boto3SQSInstrumentor().uninstrument()

    def test_instrument_api_before_client_init(self) -> None:
        for session in (False, True):
            with self._active_instrumentor():
                client = _make_sqs_client(session=session)
                self._assert_instrumented(client)
            self._assert_uninstrumented(client)

    def test_instrument_api_after_client_init(self) -> None:
        for session in (False, True):
            client = _make_sqs_client(session=session)
            with self._active_instrumentor():
                self._assert_instrumented(client)
            self._assert_uninstrumented(client)

    def test_instrument_multiple_clients(self):
        for session in (False, True):
            with self._active_instrumentor():
                self._assert_instrumented(_make_sqs_client(session=session))
                self._assert_instrumented(_make_sqs_client(session=session))

    def test_instrument_api_before_resource_init(self) -> None:
        for session in (False, True):
            with self._active_instrumentor():
                sqs = _make_sqs_resource(session=session)
                self._assert_instrumented(sqs.meta.client)
            self._assert_uninstrumented(sqs.meta.client)

    def test_instrument_api_after_resource_init(self) -> None:
        for session in (False, True):
            sqs = _make_sqs_resource(session=session)
            with self._active_instrumentor():
                self._assert_instrumented(sqs.meta.client)
            self._assert_uninstrumented(sqs.meta.client)

    def test_instrument_multiple_resources(self):
        for session in (False, True):
            with self._active_instrumentor():
                self._assert_instrumented(_make_sqs_resource(session=session).meta.client)
                self._assert_instrumented(_make_sqs_resource(session=session).meta.client)


class TestBoto3SQSGetter(TestCase):
    def setUp(self) -> None:
        self.getter = Boto3SQSGetter()

    def test_get_none(self) -> None:
        carrier = {}
        value = self.getter.get(carrier, "test")
        self.assertIsNone(value)

    def test_get_value(self) -> None:
        key = "test"
        value = "value"
        carrier = {key: {"StringValue": value, "DataType": "String"}}
        val = self.getter.get(carrier, key)
        self.assertEqual(val, [value])

    def test_keys(self):
        carrier = {
            "test1": {"StringValue": "value1", "DataType": "String"},
            "test2": {"StringValue": "value2", "DataType": "String"},
        }
        keys = self.getter.keys(carrier)
        self.assertEqual(keys, list(carrier.keys()))

    def test_keys_empty(self):
        keys = self.getter.keys({})
        self.assertEqual(keys, [])


class TestBoto3SQSSetter(TestCase):
    def setUp(self) -> None:
        self.setter = Boto3SQSSetter()

    def test_simple(self):
        original_key = "SomeHeader"
        original_value = {"NumberValue": 1, "DataType": "Number"}
        carrier = {original_key: original_value.copy()}
        key = "test"
        value = "value"
        self.setter.set(carrier, key, value)
        # Ensure the original value is not harmed
        for dict_key, dict_val in carrier[original_key].items():
            self.assertEqual(original_value[dict_key], dict_val)
        # Ensure the new key is added well
        self.assertEqual(carrier[key]["StringValue"], value)


class TestBoto3SQSInstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        self._reset_instrumentor()
        Boto3SQSInstrumentor().instrument()

        self._client = _make_sqs_client()
        self._queue_name = "MyQueue"
        self._queue_url = f"https://sqs.us-east-1.amazonaws.com/123456789012/{self._queue_name}"

    def tearDown(self):
        super().tearDown()
        Boto3SQSInstrumentor().uninstrument()
        self._reset_instrumentor()

    @staticmethod
    def _reset_instrumentor():
        Boto3SQSInstrumentor._clear_processing_spans()

    @staticmethod
    def _make_aws_response_func(response):
        def _response_func(*args, **kwargs):
            return AWSResponse("http://127.0.0.1", 200, {}, "{}"), response

        return _response_func

    @contextmanager
    def _mocked_endpoint(self, response):
        response_func = self._make_aws_response_func(response)
        with mock.patch("botocore.endpoint.Endpoint.make_request", new=response_func):
            yield

    def _assert_injected_span(self, msg_attrs: dict[str, Any], span: Span):
        trace_parent = msg_attrs["traceparent"]["StringValue"]
        ctx = span.get_span_context()
        self.assertEqual(
            self._to_trace_parent(ctx.trace_id, ctx.span_id, ctx.trace_flags),
            trace_parent.lower(),
        )

    def _default_span_attrs(self):
        return {
            messaging_attributes.MESSAGING_SYSTEM: "aws.sqs",
            SpanAttributes.MESSAGING_DESTINATION: self._queue_name,
            SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
            SpanAttributes.MESSAGING_URL: self._queue_url,
        }

    @staticmethod
    def _to_trace_parent(trace_id: int, span_id: int, trace_flags: TraceFlags) -> str:
        return f"00-{format_trace_id(trace_id)}-{format_span_id(span_id)}-{trace_flags:02x}".lower()

    def _get_only_span(self):
        spans = self.get_finished_spans()
        self.assertEqual(1, len(spans))
        return spans[0]

    @staticmethod
    def _make_message(message_id: str, body: str, receipt: str):
        return {
            "MessageId": message_id,
            "ReceiptHandle": receipt,
            "MD5OfBody": "777",
            "Body": body,
            "Attributes": {},
            "MD5OfMessageAttributes": "111",
            "MessageAttributes": {},
        }

    def _add_trace_parent(self, message: dict[str, Any], trace_id: int, span_id: int):
        message["MessageAttributes"]["traceparent"] = {
            "StringValue": self._to_trace_parent(trace_id, span_id, TraceFlags.get_default()),
            "DataType": "String",
        }

    def test_send_message(self):
        message_id = "123456789"
        mock_response = {
            "MD5OfMessageBody": "1234",
            "MD5OfMessageAttributes": "5678",
            "MD5OfMessageSystemAttributes": "9012",
            "MessageId": message_id,
            "SequenceNumber": "0",
        }

        message_attrs = {}

        with self._mocked_endpoint(mock_response):
            self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody="hello msg",
                MessageAttributes=message_attrs,
            )

        span = self._get_only_span()
        self.assertEqual(f"{self._queue_name} send", span.name)
        self.assertEqual(SpanKind.PRODUCER, span.kind)
        self.assertEqual(
            {
                messaging_attributes.MESSAGING_MESSAGE_ID: message_id,
                **self._default_span_attrs(),
            },
            span.attributes,
        )
        self._assert_injected_span(message_attrs, span)

    def test_send_message_batch(self):
        expected_message_ids = {"1": "msg-1", "2": "msg-2"}
        mock_response = {
            "Successful": [
                {"Id": "1", "MessageId": "msg-1", "MD5OfMessageBody": "11"},
                {"Id": "2", "MessageId": "msg-2", "MD5OfMessageBody": "22"},
            ],
            "Failed": [],
        }
        entries = [
            {"Id": "1", "MessageBody": "hello 1"},
            {"Id": "2", "MessageBody": "hello 2"},
        ]

        with self._mocked_endpoint(mock_response):
            self._client.send_message_batch(QueueUrl=self._queue_url, Entries=entries)

        spans = self.get_finished_spans()
        self.assertEqual(2, len(spans))
        spans_by_entry_id = {span.attributes[SpanAttributes.MESSAGING_CONVERSATION_ID]: span for span in spans}
        for entry in entries:
            entry_id = entry["Id"]
            span = spans_by_entry_id[entry_id]
            self.assertEqual(f"{self._queue_name} send", span.name)
            self.assertEqual(SpanKind.PRODUCER, span.kind)
            self.assertEqual(
                {
                    SpanAttributes.MESSAGING_CONVERSATION_ID: entry_id,
                    messaging_attributes.MESSAGING_MESSAGE_ID: expected_message_ids[entry_id],
                    **self._default_span_attrs(),
                },
                span.attributes,
            )
            self._assert_injected_span(entry["MessageAttributes"], span)

    def test_send_message_batch_all_failed(self):
        mock_response = {
            "Failed": [
                {
                    "Id": "1",
                    "SenderFault": True,
                    "Code": "InvalidParameterValue",
                    "Message": "boom",
                }
            ]
        }
        entries = [{"Id": "1", "MessageBody": "hello 1"}]

        with self._mocked_endpoint(mock_response):
            self._client.send_message_batch(QueueUrl=self._queue_url, Entries=entries)

        span = self._get_only_span()
        self.assertEqual(f"{self._queue_name} send", span.name)
        self.assertEqual(SpanKind.PRODUCER, span.kind)
        self.assertEqual(
            {
                SpanAttributes.MESSAGING_CONVERSATION_ID: "1",
                **self._default_span_attrs(),
            },
            span.attributes,
        )
        self.assertNotIn(messaging_attributes.MESSAGING_MESSAGE_ID, span.attributes)
        self._assert_injected_span(entries[0]["MessageAttributes"], span)

    def test_receive_message(self):
        msg_def = {
            "1": {"receipt": "01", "trace_id": 10, "span_id": 1},
            "2": {"receipt": "02", "trace_id": 20, "span_id": 2},
        }

        mock_response = {"Messages": []}
        for msg_id, attrs in msg_def.items():
            message = self._make_message(msg_id, f"hello {msg_id}", attrs["receipt"])
            self._add_trace_parent(message, attrs["trace_id"], attrs["span_id"])
            mock_response["Messages"].append(message)

        message_attr_names = []

        with self._mocked_endpoint(mock_response):
            response = self._client.receive_message(
                QueueUrl=self._queue_url,
                MessageAttributeNames=message_attr_names,
            )

        self.assertIn("traceparent", message_attr_names)

        # receive span
        span = self._get_only_span()
        receive_span = span
        self.assertEqual(f"{self._queue_name} receive", span.name)
        self.assertEqual(SpanKind.CONSUMER, span.kind)
        self.assertEqual(
            {
                SpanAttributes.MESSAGING_OPERATION: MessagingOperationValues.RECEIVE.value,
                **self._default_span_attrs(),
            },
            span.attributes,
        )
        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)

        self.memory_exporter.clear()

        # processing spans
        self.assertEqual(2, len(response["Messages"]))
        for msg in response["Messages"]:
            msg_id = msg["MessageId"]
            attrs = msg_def[msg_id]
            with self._mocked_endpoint({}):
                self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=attrs["receipt"])

            span = self._get_only_span()
            self.assertEqual(f"{self._queue_name} process", span.name)
            self.assertEqual(
                receive_span.get_span_context().trace_id,
                span.get_span_context().trace_id,
            )
            self.assertEqual(receive_span.get_span_context().span_id, span.parent.span_id)

            # processing span attributes
            self.assertEqual(
                {
                    messaging_attributes.MESSAGING_MESSAGE_ID: msg_id,
                    SpanAttributes.MESSAGING_OPERATION: MessagingOperationValues.PROCESS.value,
                    **self._default_span_attrs(),
                },
                span.attributes,
            )

            # processing span links
            self.assertEqual(1, len(span.links))
            link = span.links[0]
            self.assertEqual(attrs["trace_id"], link.context.trace_id)
            self.assertEqual(attrs["span_id"], link.context.span_id)

            self.memory_exporter.clear()

    def test_processing_spans_start_on_access_and_end_on_next_message(self):
        messages = [
            self._make_message("1", "hello 1", "receipt-1"),
            self._make_message("2", "hello 2", "receipt-2"),
        ]

        with self._mocked_endpoint({"Messages": messages}):
            response = self._client.receive_message(QueueUrl=self._queue_url)

        receive_span = self._get_only_span()
        self.memory_exporter.clear()

        _ = response["Messages"][0]
        first_processing_span = Boto3SQSInstrumentor.received_messages_spans["receipt-1"].span
        self.assertGreater(first_processing_span.start_time, receive_span.end_time)
        self.assertEqual([], self.get_finished_spans())

        _ = response["Messages"][1]
        second_processing_span = Boto3SQSInstrumentor.received_messages_spans["receipt-2"].span
        self.assertNotIn("receipt-1", Boto3SQSInstrumentor.received_messages_spans)
        self.assertGreaterEqual(second_processing_span.start_time, first_processing_span.end_time)

        with self._mocked_endpoint({}):
            self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle="receipt-2")

        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)
        self.assertEqual(2, len(self.get_finished_spans()))

    def test_repeated_access_does_not_create_duplicate_processing_span(self):
        messages = [
            self._make_message("1", "hello 1", "receipt-1"),
            self._make_message("2", "hello 2", "receipt-2"),
        ]

        with self._mocked_endpoint({"Messages": messages}):
            response = self._client.receive_message(QueueUrl=self._queue_url)

        self._get_only_span()
        self.memory_exporter.clear()

        _ = response["Messages"][0]
        _ = response["Messages"][1]
        _ = response["Messages"][0]

        with self._mocked_endpoint({}):
            self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle="receipt-2")

        process_spans = [span for span in self.get_finished_spans() if span.name.endswith(" process")]
        self.assertEqual(2, len(process_spans))
        self.assertEqual(
            {"1", "2"},
            {span.attributes[messaging_attributes.MESSAGING_MESSAGE_ID] for span in process_spans},
        )
        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)

    def test_processing_spans_are_isolated_between_contexts(self):
        message_a = self._make_message("a", "hello a", "receipt-a")
        with self._mocked_endpoint({"Messages": [message_a]}):
            response_a = self._client.receive_message(QueueUrl=self._queue_url)
        receive_span_a = self._get_only_span()
        self.memory_exporter.clear()

        message_b = self._make_message("b", "hello b", "receipt-b")
        with self._mocked_endpoint({"Messages": [message_b]}):
            response_b = self._client.receive_message(QueueUrl=self._queue_url)
        receive_span_b = self._get_only_span()
        self.memory_exporter.clear()

        context_a = copy_context()
        context_b = copy_context()

        def access_message(response):
            _ = response["Messages"][0]

        context_a.run(access_message, response_a)
        context_b.run(access_message, response_b)

        self.assertIn("receipt-a", Boto3SQSInstrumentor.received_messages_spans)
        self.assertIn("receipt-b", Boto3SQSInstrumentor.received_messages_spans)

        def delete_message(receipt_handle):
            with self._mocked_endpoint({}):
                self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)

        context_a.run(delete_message, "receipt-a")
        context_b.run(delete_message, "receipt-b")

        process_spans = [span for span in self.get_finished_spans() if span.name.endswith(" process")]
        self.assertEqual(2, len(process_spans))
        spans_by_message_id = {
            span.attributes[messaging_attributes.MESSAGING_MESSAGE_ID]: span for span in process_spans
        }
        self.assertEqual(
            receive_span_a.get_span_context().trace_id,
            spans_by_message_id["a"].get_span_context().trace_id,
        )
        self.assertEqual(
            receive_span_a.get_span_context().span_id,
            spans_by_message_id["a"].parent.span_id,
        )
        self.assertEqual(
            receive_span_b.get_span_context().trace_id,
            spans_by_message_id["b"].get_span_context().trace_id,
        )
        self.assertEqual(
            receive_span_b.get_span_context().span_id,
            spans_by_message_id["b"].parent.span_id,
        )
        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)

    def test_unread_redeliveries_do_not_retain_message_metadata(self):
        unread_receipt = "receipt-2-0"
        for round_number in range(10):
            messages = [
                self._make_message("1", "hello 1", f"receipt-1-{round_number}"),
                self._make_message("2", "hello 2", f"receipt-2-{round_number}"),
            ]
            with self._mocked_endpoint({"Messages": messages}):
                response = self._client.receive_message(QueueUrl=self._queue_url)

            self.assertEqual(2, len(response["Messages"]))
            if round_number == 0:
                _ = response["Messages"][0]
                self.assertIn("receipt-1-0", Boto3SQSInstrumentor.received_messages_spans)
            else:
                self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)
            self.assertFalse(hasattr(Boto3SQSInstrumentor, "pending_message_metadata"))
            self.assertNotIn(unread_receipt, Boto3SQSInstrumentor.received_messages_spans)

        message = self._make_message("3", "hello 3", "receipt-3")
        with self._mocked_endpoint({"Messages": [message]}):
            response = self._client.receive_message(QueueUrl=self._queue_url)

        _ = response["Messages"][0]
        with self._mocked_endpoint({}):
            self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle="receipt-3")

        process_spans = [span for span in self.get_finished_spans() if span.name.endswith(" process")]
        self.assertEqual(2, len(process_spans))
        self.assertEqual(
            {"1", "3"},
            {span.attributes[messaging_attributes.MESSAGING_MESSAGE_ID] for span in process_spans},
        )
        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)

    def test_uninstrument_cleans_active_processing_state(self):
        message = self._make_message("1", "hello 1", "receipt-1")
        with self._mocked_endpoint({"Messages": [message]}):
            response = self._client.receive_message(QueueUrl=self._queue_url)

        _ = response["Messages"][0]
        self.assertIn("receipt-1", Boto3SQSInstrumentor.received_messages_spans)

        Boto3SQSInstrumentor().uninstrument()

        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)
        self.assertIsNone(_active_processing_span.get())

        self.memory_exporter.clear()
        _ = response["Messages"][0]
        self.assertEqual([], self.get_finished_spans())
        self.assertEqual({}, Boto3SQSInstrumentor.received_messages_spans)

    def test_uninstrument(self):
        mock_response = {
            "MessageId": "123456789",
        }

        with self._mocked_endpoint(mock_response):
            self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody="test",
            )

            spans = self.get_finished_spans()
            self.assertEqual(1, len(spans))

            self.memory_exporter.clear()
            Boto3SQSInstrumentor().uninstrument()

            self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody="test",
            )
            spans = self.get_finished_spans()
            self.assertEqual(0, len(spans))
