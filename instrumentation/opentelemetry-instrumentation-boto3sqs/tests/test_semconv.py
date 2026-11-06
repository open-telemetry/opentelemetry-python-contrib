# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=no-name-in-module

import os
from contextlib import contextmanager
from unittest import mock

import boto3
from botocore.awsrequest import AWSResponse

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    MessagingOperationValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


def stability_mode(mode):
    def decorator(test_case):
        def wrapper(*args, **kwargs):
            with mock.patch.dict(os.environ, {OTEL_SEMCONV_STABILITY_OPT_IN: mode}):
                _OpenTelemetrySemanticConventionStability._initialized = False
                _OpenTelemetrySemanticConventionStability._initialize()
                try:
                    return test_case(*args, **kwargs)
                finally:
                    # Restore the default (old conventions) state so other
                    # tests in the same process are not affected.
                    _OpenTelemetrySemanticConventionStability._initialized = False
                    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
                    _OpenTelemetrySemanticConventionStability._initialize()

        return wrapper

    return decorator


def _make_sqs_client():
    return boto3.client(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
    )


class TestBoto3SQSSemConv(TestBase):
    def setUp(self):
        super().setUp()
        self._reset_instrumentor()
        self._client = _make_sqs_client()
        self._queue_name = "MyQueue"
        self._queue_url = f"https://sqs.us-east-1.amazonaws.com/123456789012/{self._queue_name}"

    def tearDown(self):
        super().tearDown()
        Boto3SQSInstrumentor().uninstrument()
        self._reset_instrumentor()

    @staticmethod
    def _reset_instrumentor():
        Boto3SQSInstrumentor.received_messages_spans.clear()
        Boto3SQSInstrumentor.current_span_related_to_token = None
        Boto3SQSInstrumentor.current_context_token = None

    @staticmethod
    def _make_aws_response_func(response):
        def _response_func(*args, **kwargs):
            return AWSResponse("http://127.0.0.1", 200, {}, "{}"), response

        return _response_func

    @contextmanager
    def _mocked_endpoint(self, response):
        with mock.patch(
            "botocore.endpoint.Endpoint.make_request",
            new=self._make_aws_response_func(response),
        ):
            yield

    @contextmanager
    def _active_instrumentor(self):
        Boto3SQSInstrumentor().instrument()
        try:
            yield
        finally:
            Boto3SQSInstrumentor().uninstrument()
            self._reset_instrumentor()

    def _new_attrs(self):
        return {
            messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.AWS_SQS.value,
            messaging_attributes.MESSAGING_DESTINATION_NAME: self._queue_name,
        }

    def _old_attrs(self):
        return {
            messaging_attributes.MESSAGING_SYSTEM: "aws.sqs",
            SpanAttributes.MESSAGING_DESTINATION: self._queue_name,
            SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
            SpanAttributes.MESSAGING_URL: self._queue_url,
        }

    def _send_message(self):
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
        spans = self.get_finished_spans()
        self.assertEqual(1, len(spans))
        return spans[0], message_id

    @stability_mode("messaging")
    def test_send_message_new_mode(self):
        with self._active_instrumentor():
            span, message_id = self._send_message()
        self.assertEqual(f"{self._queue_name} send", span.name)
        self.assertEqual(SpanKind.PRODUCER, span.kind)
        self.assertEqual(
            {
                messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.SEND.value,
                messaging_attributes.MESSAGING_OPERATION_NAME: messaging_attributes.MessagingOperationTypeValues.SEND.value,
                messaging_attributes.MESSAGING_MESSAGE_ID: message_id,
                **self._new_attrs(),
            },
            span.attributes,
        )

    @stability_mode("messaging/dup")
    def test_send_message_dup_mode(self):
        with self._active_instrumentor():
            span, message_id = self._send_message()
        self.assertEqual(f"{self._queue_name} send", span.name)
        self.assertEqual(SpanKind.PRODUCER, span.kind)
        # messaging.system cannot carry both values in dup mode; the new
        # value wins (see _enrich_span). Old destination/kind/url are kept.
        self.assertEqual(
            {
                messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.SEND.value,
                messaging_attributes.MESSAGING_OPERATION_NAME: messaging_attributes.MessagingOperationTypeValues.SEND.value,
                messaging_attributes.MESSAGING_MESSAGE_ID: message_id,
                messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.AWS_SQS.value,
                SpanAttributes.MESSAGING_DESTINATION: self._queue_name,
                SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                SpanAttributes.MESSAGING_URL: self._queue_url,
                messaging_attributes.MESSAGING_DESTINATION_NAME: self._queue_name,
            },
            span.attributes,
        )

    @stability_mode("messaging")
    def test_receive_and_process_new_mode(self):
        message = {
            "MessageId": "msg-1",
            "ReceiptHandle": "01",
            "MD5OfBody": "777",
            "Body": "hello 1",
            "Attributes": {},
            "MD5OfMessageAttributes": "111",
            "MessageAttributes": {},
        }
        with self._active_instrumentor():
            with self._mocked_endpoint({"Messages": [message]}):
                response = self._client.receive_message(QueueUrl=self._queue_url)
            spans = self.get_finished_spans()
            self.assertEqual(1, len(spans))
            receive_span = spans[0]
            self.assertEqual(f"{self._queue_name} receive", receive_span.name)
            self.assertEqual(SpanKind.CONSUMER, receive_span.kind)
            self.assertEqual(
                {
                    messaging_attributes.MESSAGING_OPERATION_TYPE: MessagingOperationValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_OPERATION_NAME: MessagingOperationValues.RECEIVE.value,
                    **self._new_attrs(),
                },
                receive_span.attributes,
            )
            self.memory_exporter.clear()
            # Iterating attaches the processing span's context; deleting
            # ends it so its attributes can be asserted.
            for _msg in response["Messages"]:
                pass
            # An empty dict (not None): botocore >= 1.43 crashes in its
            # SQS error-compat handler when the mocked parsed response
            # is None — the same environment-only failure that makes the
            # pre-existing test_receive_message fail on the pristine tree.
            with self._mocked_endpoint({}):
                self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle="01")
            spans = self.get_finished_spans()
            self.assertEqual(1, len(spans))
            process_span = spans[0]
            self.assertEqual(f"{self._queue_name} process", process_span.name)
            self.assertEqual(
                {
                    messaging_attributes.MESSAGING_OPERATION_TYPE: MessagingOperationValues.PROCESS.value,
                    messaging_attributes.MESSAGING_OPERATION_NAME: MessagingOperationValues.PROCESS.value,
                    messaging_attributes.MESSAGING_MESSAGE_ID: "msg-1",
                    **self._new_attrs(),
                },
                process_span.attributes,
            )
