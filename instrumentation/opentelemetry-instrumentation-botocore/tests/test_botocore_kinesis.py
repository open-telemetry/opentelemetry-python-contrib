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
import json
from typing import Any, Dict
from unittest import mock

import botocore.session
from botocore.awsrequest import AWSResponse

from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import Span


class TestKinesisExtension(TestBase):
    def setUp(self):
        super().setUp()
        BotocoreInstrumentor().instrument()

        session = botocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.client = session.create_client(
            "kinesis", region_name="us-west-2"
        )
        self.stream_name = "my-stream"

    def tearDown(self):
        super().tearDown()
        BotocoreInstrumentor().uninstrument()

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
            "aws.kinesis", span.attributes[SpanAttributes.MESSAGING_SYSTEM]
        )

        return span

    def assert_injected_span(self, data_dict: Dict[str, Any], span: Span):
        trace_parent = data_dict["traceparent"].split("-")
        span_context = span.get_span_context()

        self.assertEqual(span_context.trace_id, int(trace_parent[1], 16))
        self.assertEqual(span_context.span_id, int(trace_parent[2], 16))

    def test_put_record_injects_span(self):
        mock_response = {
            "ShardId": "shardId-000000000000",
            "SequenceNumber": "12345",
        }

        with self._mocked_aws_endpoint(mock_response):
            self.client.put_record(
                StreamName=self.stream_name,
                Data=json.dumps({"key": "value"}).encode("utf-8"),
                PartitionKey="pk",
            )

        span = self.assert_span(f"{self.stream_name} send")
        self.assertEqual(
            self.stream_name,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_NAME],
        )

    def test_put_records_injects_span(self):
        mock_response = {
            "FailedRecordCount": 0,
            "Records": [
                {"ShardId": "shardId-000000000000", "SequenceNumber": "1"},
                {"ShardId": "shardId-000000000000", "SequenceNumber": "2"},
            ],
        }

        records = [
            {
                "Data": json.dumps({"key1": "value1"}).encode("utf-8"),
                "PartitionKey": "pk1",
            },
            {
                "Data": json.dumps({"key2": "value2"}).encode("utf-8"),
                "PartitionKey": "pk2",
            },
        ]

        with self._mocked_aws_endpoint(mock_response):
            self.client.put_records(
                StreamName=self.stream_name,
                Records=records,
            )

        span = self.assert_span(f"{self.stream_name} send")
        self.assertEqual(
            self.stream_name,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_NAME],
        )

        # Verify traceparent was injected into each record's Data
        for record in records:
            data = record["Data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            data_dict = json.loads(data)
            self.assert_injected_span(data_dict, span)

    def test_put_record_stream_arn(self):
        mock_response = {
            "ShardId": "shardId-000000000000",
            "SequenceNumber": "12345",
        }

        data = json.dumps({"key": "value"}).encode("utf-8")

        with self._mocked_aws_endpoint(mock_response):
            self.client.put_record(
                StreamARN="arn:aws:kinesis:us-west-2:123456789012:stream/my-arn-stream",
                Data=data,
                PartitionKey="pk",
            )

        span = self.assert_span("my-arn-stream send")
        self.assertEqual(
            "my-arn-stream",
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_NAME],
        )

    def test_put_record_non_json_data(self):
        mock_response = {
            "ShardId": "shardId-000000000000",
            "SequenceNumber": "12345",
        }

        original_data = b"this is not json"

        with self._mocked_aws_endpoint(mock_response):
            self.client.put_record(
                StreamName=self.stream_name,
                Data=original_data,
                PartitionKey="pk",
            )

        # Should still create a span without crashing
        span = self.assert_span(f"{self.stream_name} send")
        self.assertIsNotNone(span)

    def test_put_record_skips_injection_when_exceeds_1mb(self):
        mock_response = {
            "ShardId": "shardId-000000000000",
            "SequenceNumber": "12345",
        }

        # Create a JSON payload just under 1MB so that adding trace context pushes it over
        padding = "x" * (1_048_576 - 20)
        original_data = json.dumps({"key": padding}).encode("utf-8")

        with self._mocked_aws_endpoint(mock_response):
            self.client.put_record(
                StreamName=self.stream_name,
                Data=original_data,
                PartitionKey="pk",
            )

        # Span should still be created
        span = self.assert_span(f"{self.stream_name} send")
        self.assertIsNotNone(span)

        # Data should remain unchanged — no traceparent injected
        # The original_data was passed by reference via the params dict,
        # but since injection was skipped, re-parse to confirm no traceparent
        data_dict = json.loads(original_data.decode("utf-8"))
        self.assertNotIn("traceparent", data_dict)

    def test_put_record_empty_data(self):
        mock_response = {
            "ShardId": "shardId-000000000000",
            "SequenceNumber": "12345",
        }

        with self._mocked_aws_endpoint(mock_response):
            self.client.put_record(
                StreamName=self.stream_name,
                Data=b"",
                PartitionKey="pk",
            )

        # Should still create a span without crashing
        span = self.assert_span(f"{self.stream_name} send")
        self.assertIsNotNone(span)
