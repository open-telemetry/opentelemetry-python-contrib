# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
from typing import Any, Dict
from unittest import mock

import botocore.session
from botocore.awsrequest import AWSResponse
from moto import mock_sns

from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import Span


class TestSnsExtension(TestBase):
    def setUp(self):
        super().setUp()
        BotocoreInstrumentor().instrument()

        session = botocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.client = session.create_client("sns", region_name="us-west-2")
        self.topic_name = "my-topic"

    def tearDown(self):
        super().tearDown()
        BotocoreInstrumentor().uninstrument()

    def _create_topic(self, name: str = None) -> str:
        if name is None:
            name = self.topic_name

        response = self.client.create_topic(Name=name)

        self.memory_exporter.clear()
        return response["TopicArn"]

    @contextlib.contextmanager
    def _mocked_aws_endpoint(self, response):
        response_func = self._make_aws_response_func(response)
        with mock.patch(
            "botocore.endpoint.Endpoint.make_request", new=response_func
        ):
            yield

    @staticmethod
    def _make_aws_response_func(response):
        def _response_func(*args, **kwargs):
            return AWSResponse("http://127.0.0.1", 200, {}, "{}"), response

        return _response_func

    def assert_span(self, name: str) -> Span:
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        span = spans[0]

        self.assertEqual(SpanKind.PRODUCER, span.kind)
        self.assertEqual(name, span.name)
        self.assertEqual(
            "aws.sns", span.attributes[SpanAttributes.MESSAGING_SYSTEM]
        )

        return span

    def assert_injected_span(self, message_attrs: Dict[str, Any], span: Span):
        # traceparent: <ver>-<trace-id>-<span-id>-<flags>
        trace_parent = message_attrs["traceparent"]["StringValue"].split("-")
        span_context = span.get_span_context()

        self.assertEqual(span_context.trace_id, int(trace_parent[1], 16))
        self.assertEqual(span_context.span_id, int(trace_parent[2], 16))

    @mock_sns
    def test_publish_to_topic_arn(self):
        self._test_publish_to_arn("TopicArn")

    @mock_sns
    def test_publish_to_target_arn(self):
        self._test_publish_to_arn("TargetArn")

    def _test_publish_to_arn(self, arg_name: str):
        target_arn = self._create_topic(self.topic_name)

        self.client.publish(
            **{
                arg_name: target_arn,
                "Message": "Hello message",
            }
        )

        span = self.assert_span(f"{self.topic_name} send")
        self.assertEqual(
            MessagingDestinationKindValues.TOPIC.value,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_KIND],
        )
        self.assertEqual(
            self.topic_name,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION],
        )

    @mock_sns
    def test_publish_to_phone_number(self):
        phone_number = "+10000000000"
        self.client.publish(
            PhoneNumber=phone_number,
            Message="Hello SNS",
        )

        span = self.assert_span("phone_number send")
        self.assertEqual(
            phone_number, span.attributes[SpanAttributes.MESSAGING_DESTINATION]
        )

    @mock_sns
    def test_publish_injects_span(self):
        message_attrs = {}
        topic_arn = self._create_topic()
        self.client.publish(
            TopicArn=topic_arn,
            Message="Hello Message",
            MessageAttributes=message_attrs,
        )

        span = self.assert_span(f"{self.topic_name} send")
        self.assert_injected_span(message_attrs, span)

    def test_publish_batch_to_topic(self):
        topic_arn = f"arn:aws:sns:region:000000000:{self.topic_name}"
        message1_attrs = {}
        message2_attrs = {}
        mock_response = {
            "Successful": [
                {"Id": "1", "MessageId": "11", "SequenceNumber": "1"},
                {"Id": "2", "MessageId": "22", "SequenceNumber": "2"},
            ],
            "Failed": [],
        }

        # publish_batch not implemented by moto so mock the endpoint instead
        with self._mocked_aws_endpoint(mock_response):
            self.client.publish_batch(
                TopicArn=topic_arn,
                PublishBatchRequestEntries=[
                    {
                        "Id": "1",
                        "Message": "Hello message 1",
                        "MessageAttributes": message1_attrs,
                    },
                    {
                        "Id": "2",
                        "Message": "Hello message 2",
                        "MessageAttributes": message2_attrs,
                    },
                ],
            )

        span = self.assert_span(f"{self.topic_name} send")
        self.assertEqual(
            MessagingDestinationKindValues.TOPIC.value,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_KIND],
        )
        self.assertEqual(
            self.topic_name,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION],
        )

        self.assert_injected_span(message1_attrs, span)
        self.assert_injected_span(message2_attrs, span)
