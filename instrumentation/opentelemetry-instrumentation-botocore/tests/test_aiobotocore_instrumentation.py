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

# pylint:disable=too-many-public-methods
import asyncio
import json
from typing import Any
from unittest.mock import Mock, patch

import aiobotocore.session
import botocore.stub
from botocore.exceptions import ClientError

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.botocore import AiobotocoreInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes.cloud_attributes import (
    CLOUD_REGION,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_STATUS_CODE,
)
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_METHOD,
    RPC_SERVICE,
    RPC_SYSTEM,
)
from opentelemetry.semconv.attributes.exception_attributes import (
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase

_REQUEST_ID_REGEX_MATCH = r"[A-Za-z0-9]{52}"


class TestAiobotocoreInstrumentor(TestBase):
    """Aiobotocore integration testsuite"""

    def setUp(self):
        super().setUp()
        AiobotocoreInstrumentor().instrument()
        self.session = aiobotocore.session.get_session()
        self.session.set_credentials(
            access_key="access-key",
            secret_key="secret-key",
        )
        self.region = "us-west-2"

    def tearDown(self):
        super().tearDown()
        AiobotocoreInstrumentor().uninstrument()

    def _default_span_attributes(self, service: str, operation: str):
        return {
            RPC_SYSTEM: "aws-api",
            RPC_SERVICE: service,
            RPC_METHOD: operation,
            CLOUD_REGION: self.region,
            "retry_attempts": 0,
            HTTP_STATUS_CODE: 200,
            SERVER_ADDRESS: f"{service.lower()}.{self.region}.amazonaws.com",
            SERVER_PORT: 443,
        }

    def assert_only_span(self):
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        return spans[0]

    def assert_span(
        self,
        service: str,
        operation: str,
        request_id=None,
        attributes=None,
    ):
        span = self.assert_only_span()
        expected = self._default_span_attributes(service, operation)
        if attributes:
            expected.update(attributes)

        span_attributes_request_id = "aws.request_id"
        if request_id is _REQUEST_ID_REGEX_MATCH:
            actual_request_id = span.attributes[span_attributes_request_id]
            self.assertRegex(actual_request_id, _REQUEST_ID_REGEX_MATCH)
            expected[span_attributes_request_id] = actual_request_id
        elif request_id is not None:
            expected[span_attributes_request_id] = request_id

        self.assertSpanHasAttributes(span, expected)
        self.assertEqual(f"{service}.{operation}", span.name)
        return span

    def _make_client(self, service: str):
        return self.session.create_client(service, region_name=self.region)

    @staticmethod
    def _make_response_meta(request_id: str) -> dict[str, Any]:
        return {
            "RequestId": request_id,
            "RetryAttempts": 0,
            "HTTPStatusCode": 200,
        }

    def test_traced_client_ec2(self):
        """Test basic EC2 client tracing with stubbed response."""
        request_id = "fdcdcab1-ae5c-489e-9c33-4637c5dda355"

        async def _test():
            async with self._make_client("ec2") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "describe_instances",
                        {
                            "Reservations": [],
                            "ResponseMetadata": self._make_response_meta(
                                request_id
                            ),
                        },
                    )
                    await client.describe_instances()

        asyncio.run(_test())
        self.assert_span("EC2", "DescribeInstances", request_id=request_id)

    def test_traced_client_s3(self):
        """Test S3 client tracing with stubbed response."""
        request_id = "s3-request-id-12345"

        async def _test():
            async with self._make_client("s3") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "list_buckets",
                        {
                            "Buckets": [],
                            "Owner": {"ID": "owner-id"},
                            "ResponseMetadata": self._make_response_meta(
                                request_id
                            ),
                        },
                    )
                    await client.list_buckets()

        asyncio.run(_test())
        self.assert_span("S3", "ListBuckets", request_id=request_id)

    def test_no_op_tracer_provider(self):
        """Test that no spans are created when using NoOpTracerProvider."""
        AiobotocoreInstrumentor().uninstrument()
        AiobotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        async def _test():
            async with self._make_client("ec2") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "describe_instances",
                        {
                            "Reservations": [],
                            "ResponseMetadata": self._make_response_meta(
                                "test-id"
                            ),
                        },
                    )
                    await client.describe_instances()

        asyncio.run(_test())
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_not_recording(self):
        """Test behavior when span is not recording."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span

        async def _test():
            with patch("opentelemetry.trace.get_tracer") as tracer:
                tracer.return_value = mock_tracer
                async with self._make_client("ec2") as client:
                    with botocore.stub.Stubber(client) as stubber:
                        stubber.add_response(
                            "describe_instances",
                            {
                                "Reservations": [],
                                "ResponseMetadata": self._make_response_meta(
                                    "test-id"
                                ),
                            },
                        )
                        await client.describe_instances()
                        self.assertFalse(mock_span.is_recording())
                        self.assertTrue(mock_span.is_recording.called)
                        self.assertFalse(mock_span.set_attribute.called)
                        self.assertFalse(mock_span.set_status.called)

        asyncio.run(_test())

    def test_client_error(self):
        """Test that ClientError is properly traced with error status."""

        async def _test():
            async with self._make_client("s3") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_client_error(
                        "get_object",
                        service_error_code="NoSuchKey",
                        service_message="The specified key does not exist.",
                        http_status_code=404,
                    )
                    with self.assertRaises(ClientError):
                        await client.get_object(
                            Bucket="test-bucket", Key="test-key"
                        )

        asyncio.run(_test())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        span = spans[0]

        self.assertIs(span.status.status_code, trace_api.StatusCode.ERROR)
        self.assertEqual("S3.GetObject", span.name)

        # Verify exception event was recorded
        self.assertEqual(1, len(span.events))
        event = span.events[0]
        self.assertIn(EXCEPTION_STACKTRACE, event.attributes)
        self.assertIn(EXCEPTION_TYPE, event.attributes)
        self.assertIn(EXCEPTION_MESSAGE, event.attributes)

    def test_suppress_instrumentation(self):
        """Test that instrumentation can be suppressed."""

        async def _test():
            async with self._make_client("ec2") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "describe_instances",
                        {
                            "Reservations": [],
                            "ResponseMetadata": self._make_response_meta(
                                "test-id"
                            ),
                        },
                    )
                    stubber.add_response(
                        "describe_instances",
                        {
                            "Reservations": [],
                            "ResponseMetadata": self._make_response_meta(
                                "test-id-2"
                            ),
                        },
                    )
                    with suppress_instrumentation():
                        await client.describe_instances()
                        await client.describe_instances()

        asyncio.run(_test())
        self.assertEqual(0, len(self.get_finished_spans()))

    def test_request_hook(self):
        """Test that request hook is called with correct parameters."""
        request_hook_service_attribute_name = "request_hook.service_name"
        request_hook_operation_attribute_name = "request_hook.operation_name"
        request_hook_api_params_attribute_name = "request_hook.api_params"

        def request_hook(span, service_name, operation_name, api_params):
            hook_attributes = {
                request_hook_service_attribute_name: service_name,
                request_hook_operation_attribute_name: operation_name,
                request_hook_api_params_attribute_name: json.dumps(api_params),
            }
            span.set_attributes(hook_attributes)

        AiobotocoreInstrumentor().uninstrument()
        AiobotocoreInstrumentor().instrument(request_hook=request_hook)

        request_id = "hook-test-request-id"

        async def _test():
            async with self._make_client("s3") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "list_objects_v2",
                        {
                            "Contents": [],
                            "ResponseMetadata": self._make_response_meta(
                                request_id
                            ),
                        },
                        expected_params={"Bucket": "test-bucket"},
                    )
                    await client.list_objects_v2(Bucket="test-bucket")

        asyncio.run(_test())

        self.assert_span(
            "S3",
            "ListObjectsV2",
            request_id=request_id,
            attributes={
                request_hook_service_attribute_name: "s3",
                request_hook_operation_attribute_name: "ListObjectsV2",
                request_hook_api_params_attribute_name: json.dumps(
                    {"Bucket": "test-bucket"}
                ),
            },
        )

    def test_response_hook(self):
        """Test that response hook is called with correct parameters."""
        response_hook_service_attribute_name = "response_hook.service_name"
        response_hook_operation_attribute_name = "response_hook.operation_name"
        response_hook_bucket_count_attribute_name = (
            "response_hook.bucket_count"
        )

        def response_hook(span, service_name, operation_name, result):
            hook_attributes = {
                response_hook_service_attribute_name: service_name,
                response_hook_operation_attribute_name: operation_name,
                response_hook_bucket_count_attribute_name: len(
                    result["Buckets"]
                ),
            }
            span.set_attributes(hook_attributes)

        AiobotocoreInstrumentor().uninstrument()
        AiobotocoreInstrumentor().instrument(response_hook=response_hook)

        request_id = "response-hook-test-id"

        async def _test():
            async with self._make_client("s3") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "list_buckets",
                        {
                            "Buckets": [
                                {"Name": "bucket1"},
                                {"Name": "bucket2"},
                            ],
                            "Owner": {"ID": "owner-id"},
                            "ResponseMetadata": self._make_response_meta(
                                request_id
                            ),
                        },
                    )
                    await client.list_buckets()

        asyncio.run(_test())

        self.assert_span(
            "S3",
            "ListBuckets",
            request_id=request_id,
            attributes={
                response_hook_service_attribute_name: "s3",
                response_hook_operation_attribute_name: "ListBuckets",
                response_hook_bucket_count_attribute_name: 2,
            },
        )

    def test_multiple_operations(self):
        """Test tracing multiple sequential operations."""

        async def _test():
            async with self._make_client("s3") as client:
                with botocore.stub.Stubber(client) as stubber:
                    stubber.add_response(
                        "list_buckets",
                        {
                            "Buckets": [],
                            "Owner": {"ID": "owner-id"},
                            "ResponseMetadata": self._make_response_meta(
                                "req-1"
                            ),
                        },
                    )
                    stubber.add_response(
                        "list_buckets",
                        {
                            "Buckets": [],
                            "Owner": {"ID": "owner-id"},
                            "ResponseMetadata": self._make_response_meta(
                                "req-2"
                            ),
                        },
                    )
                    await client.list_buckets()
                    await client.list_buckets()

        asyncio.run(_test())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(2, len(spans))

        for span in spans:
            self.assertEqual("S3.ListBuckets", span.name)

        self.assertEqual("req-1", spans[0].attributes["aws.request_id"])
        self.assertEqual("req-2", spans[1].attributes["aws.request_id"])
