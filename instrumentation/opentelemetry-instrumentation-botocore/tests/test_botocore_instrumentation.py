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
import json
import os
from unittest.mock import ANY, Mock, patch

import botocore.session
from botocore.exceptions import ParamValidationError
from moto import mock_aws  # pylint: disable=import-error

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.utils import (
    suppress_http_instrumentation,
    suppress_instrumentation,
)
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.propagators.aws.aws_xray_propagator import TRACE_HEADER_KEY
from opentelemetry.semconv._incubating.attributes.cloud_attributes import (
    CLOUD_REGION,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace.span import format_span_id, format_trace_id

_REQUEST_ID_REGEX_MATCH = r"[A-Za-z0-9]{52}"


# pylint:disable=too-many-public-methods
class TestBotocoreInstrumentor(TestBase):
    """Botocore integration testsuite"""

    def setUp(self):
        super().setUp()
        BotocoreInstrumentor().instrument()

        self.session = botocore.session.get_session()
        self.session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"

    def tearDown(self):
        super().tearDown()
        BotocoreInstrumentor().uninstrument()

    def _make_client(self, service: str):
        return self.session.create_client(service, region_name=self.region)

    def _default_span_attributes(self, service: str, operation: str):
        return {
            SpanAttributes.RPC_SYSTEM: "aws-api",
            SpanAttributes.RPC_SERVICE: service,
            SpanAttributes.RPC_METHOD: operation,
            CLOUD_REGION: self.region,
            "retry_attempts": 0,
            SpanAttributes.HTTP_STATUS_CODE: 200,
            # Some services like IAM or STS have a global endpoint and exclude specified region.
            SpanAttributes.SERVER_ADDRESS: f"{service.lower()}.{'' if self.region == 'aws-global' else self.region + '.'}amazonaws.com",
            SpanAttributes.SERVER_PORT: 443,
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

    @mock_aws
    def test_traced_client(self):
        ec2 = self._make_client("ec2")

        ec2.describe_instances()

        request_id = "fdcdcab1-ae5c-489e-9c33-4637c5dda355"
        self.assert_span("EC2", "DescribeInstances", request_id=request_id)

    @mock_aws
    def test_no_op_tracer_provider_ec2(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        ec2 = self._make_client("ec2")
        ec2.describe_instances()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_not_recording(self):
        mock_tracer = Mock()
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            ec2 = self._make_client("ec2")
            ec2.describe_instances()
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    @mock_aws
    def test_exception(self):
        s3 = self._make_client("s3")

        with self.assertRaises(ParamValidationError):
            s3.list_objects(bucket="mybucket")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        span = spans[0]

        expected = self._default_span_attributes("S3", "ListObjects")
        expected.pop(SpanAttributes.HTTP_STATUS_CODE)
        expected.pop("retry_attempts")
        self.assertEqual(expected, span.attributes)
        self.assertIs(span.status.status_code, trace_api.StatusCode.ERROR)

        self.assertEqual(1, len(span.events))
        event = span.events[0]
        self.assertIn(SpanAttributes.EXCEPTION_STACKTRACE, event.attributes)
        self.assertIn(SpanAttributes.EXCEPTION_TYPE, event.attributes)
        self.assertIn(SpanAttributes.EXCEPTION_MESSAGE, event.attributes)

    @mock_aws
    def test_s3_client(self):
        s3 = self._make_client("s3")

        s3.list_buckets()
        self.assert_span("S3", "ListBuckets")

    @mock_aws
    def test_no_op_tracer_provider_s3(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        s3 = self._make_client("s3")
        s3.list_buckets()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_s3_put(self):
        s3 = self._make_client("s3")

        location = {"LocationConstraint": "us-west-2"}
        s3.create_bucket(Bucket="mybucket", CreateBucketConfiguration=location)
        self.assert_span(
            "S3", "CreateBucket", request_id=_REQUEST_ID_REGEX_MATCH
        )
        self.memory_exporter.clear()

        s3.put_object(Key="foo", Bucket="mybucket", Body=b"bar")
        self.assert_span("S3", "PutObject", request_id=_REQUEST_ID_REGEX_MATCH)
        self.memory_exporter.clear()

        s3.get_object(Bucket="mybucket", Key="foo")
        self.assert_span("S3", "GetObject", request_id=_REQUEST_ID_REGEX_MATCH)

    @mock_aws
    def test_sqs_client(self):
        sqs = self._make_client("sqs")

        sqs.list_queues()

        self.assert_span(
            "SQS", "ListQueues", request_id=_REQUEST_ID_REGEX_MATCH
        )

    @mock_aws
    def test_no_op_tracer_provider_sqs(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        sqs = self._make_client("sqs")
        sqs.list_queues()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_sqs_send_message(self):
        sqs = self._make_client("sqs")
        test_queue_name = "test_queue_name"

        response = sqs.create_queue(QueueName=test_queue_name)
        self.assert_span(
            "SQS", "CreateQueue", request_id=_REQUEST_ID_REGEX_MATCH
        )
        self.memory_exporter.clear()

        queue_url = response["QueueUrl"]
        sqs.send_message(QueueUrl=queue_url, MessageBody="Test SQS MESSAGE!")

        self.assert_span(
            "SQS",
            "SendMessage",
            request_id=_REQUEST_ID_REGEX_MATCH,
            attributes={"aws.queue_url": queue_url},
        )

    @mock_aws
    def test_kinesis_client(self):
        kinesis = self._make_client("kinesis")

        kinesis.list_streams()
        self.assert_span("Kinesis", "ListStreams")

    @mock_aws
    def test_no_op_tracer_provider_kinesis(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        kinesis = self._make_client("kinesis")
        kinesis.list_streams()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_unpatch(self):
        kinesis = self._make_client("kinesis")

        BotocoreInstrumentor().uninstrument()

        kinesis.list_streams()
        self.assertEqual(0, len(self.memory_exporter.get_finished_spans()))

    @mock_aws
    def test_no_op_tracer_provider_kms(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        kms = self._make_client("kms")
        kms.list_keys(Limit=21)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_uninstrument_does_not_inject_headers(self):
        headers = {}

        def intercept_headers(**kwargs):
            headers.update(kwargs["request"].headers)

        ec2 = self._make_client("ec2")

        BotocoreInstrumentor().uninstrument()

        ec2.meta.events.register_first(
            "before-send.ec2.DescribeInstances", intercept_headers
        )
        with self.tracer_provider.get_tracer("test").start_span("parent"):
            ec2.describe_instances()

        self.assertNotIn(TRACE_HEADER_KEY, headers)

    @mock_aws
    def test_double_patch(self):
        sqs = self._make_client("sqs")

        BotocoreInstrumentor().instrument()
        BotocoreInstrumentor().instrument()

        sqs.list_queues()
        self.assert_span(
            "SQS", "ListQueues", request_id=_REQUEST_ID_REGEX_MATCH
        )

    @mock_aws
    def test_kms_client(self):
        kms = self._make_client("kms")

        kms.list_keys(Limit=21)

        span = self.assert_only_span()
        expected = self._default_span_attributes("KMS", "ListKeys")
        expected["aws.request_id"] = ANY
        # check for exact attribute set to make sure not to leak any kms secrets
        self.assertEqual(expected, dict(span.attributes))

    @mock_aws
    def test_sts_client(self):
        sts = self._make_client("sts")

        sts.get_caller_identity()

        span = self.assert_only_span()
        expected = self._default_span_attributes("STS", "GetCallerIdentity")
        expected["aws.request_id"] = ANY
        expected[SpanAttributes.SERVER_ADDRESS] = "sts.amazonaws.com"
        # check for exact attribute set to make sure not to leak any sts secrets
        self.assertEqual(expected, dict(span.attributes))

    @mock_aws
    def test_no_op_tracer_provider_sts(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        sts = self._make_client("sts")
        sts.get_caller_identity()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_propagator_injects_into_request(self):
        headers = {}
        previous_propagator = get_global_textmap()

        def check_headers(**kwargs):
            nonlocal headers
            headers = kwargs["request"].headers

        try:
            set_global_textmap(MockTextMapPropagator())

            ec2 = self._make_client("ec2")
            ec2.meta.events.register_first(
                "before-send.ec2.DescribeInstances", check_headers
            )
            ec2.describe_instances()

            request_id = "fdcdcab1-ae5c-489e-9c33-4637c5dda355"
            span = self.assert_span(
                "EC2", "DescribeInstances", request_id=request_id
            )

            # only x-ray propagation is used in HTTP requests
            self.assertIn(TRACE_HEADER_KEY, headers)
            xray_context = headers[TRACE_HEADER_KEY]
            formated_trace_id = format_trace_id(
                span.get_span_context().trace_id
            )
            formated_trace_id = (
                formated_trace_id[:8] + "-" + formated_trace_id[8:]
            )

            self.assertEqual(
                xray_context.lower(),
                f"root=1-{formated_trace_id};parent={format_span_id(span.get_span_context().span_id)};sampled=1".lower(),
            )
        finally:
            set_global_textmap(previous_propagator)

    @mock_aws
    def test_no_op_tracer_provider_xray(self):
        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        xray_client = self._make_client("xray")
        xray_client.put_trace_segments(TraceSegmentDocuments=["str1"])

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock_aws
    def test_override_xray_propagator_injects_into_request(self):
        headers = {}

        def check_headers(**kwargs):
            nonlocal headers
            headers = kwargs["request"].headers

        BotocoreInstrumentor().instrument()

        ec2 = self._make_client("ec2")
        ec2.meta.events.register_first(
            "before-send.ec2.DescribeInstances", check_headers
        )
        ec2.describe_instances()

        self.assertNotIn(MockTextMapPropagator.TRACE_ID_KEY, headers)
        self.assertNotIn(MockTextMapPropagator.SPAN_ID_KEY, headers)

    @mock_aws
    def test_suppress_instrumentation_xray_client(self):
        xray_client = self._make_client("xray")
        with suppress_instrumentation():
            xray_client.put_trace_segments(TraceSegmentDocuments=["str1"])
            xray_client.put_trace_segments(TraceSegmentDocuments=["str2"])
        self.assertEqual(0, len(self.get_finished_spans()))

    @mock_aws
    def test_suppress_http_instrumentation_xray_client(self):
        xray_client = self._make_client("xray")
        with suppress_http_instrumentation():
            xray_client.put_trace_segments(TraceSegmentDocuments=["str1"])
            xray_client.put_trace_segments(TraceSegmentDocuments=["str2"])
        self.assertEqual(2, len(self.get_finished_spans()))

    @mock_aws
    def test_request_hook(self):
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

        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(request_hook=request_hook)

        s3 = self._make_client("s3")

        params = {
            "Bucket": "mybucket",
            "CreateBucketConfiguration": {"LocationConstraint": "us-west-2"},
        }
        s3.create_bucket(**params)
        self.assert_span(
            "S3",
            "CreateBucket",
            attributes={
                request_hook_service_attribute_name: "s3",
                request_hook_operation_attribute_name: "CreateBucket",
                request_hook_api_params_attribute_name: json.dumps(params),
            },
        )

    @mock_aws
    def test_response_hook(self):
        response_hook_service_attribute_name = "request_hook.service_name"
        response_hook_operation_attribute_name = "response_hook.operation_name"
        response_hook_result_attribute_name = "response_hook.result"

        def response_hook(span, service_name, operation_name, result):
            hook_attributes = {
                response_hook_service_attribute_name: service_name,
                response_hook_operation_attribute_name: operation_name,
                response_hook_result_attribute_name: len(result["Buckets"]),
            }
            span.set_attributes(hook_attributes)

        BotocoreInstrumentor().uninstrument()
        BotocoreInstrumentor().instrument(response_hook=response_hook)

        s3 = self._make_client("s3")
        s3.list_buckets()
        self.assert_span(
            "S3",
            "ListBuckets",
            attributes={
                response_hook_service_attribute_name: "s3",
                response_hook_operation_attribute_name: "ListBuckets",
                response_hook_result_attribute_name: 0,
            },
        )

    @mock_aws
    def test_server_attributes(self):
        # Test regional endpoint
        ec2 = self._make_client("ec2")
        ec2.describe_instances()
        self.assert_span(
            "EC2",
            "DescribeInstances",
            attributes={
                SpanAttributes.SERVER_ADDRESS: f"ec2.{self.region}.amazonaws.com",
                SpanAttributes.SERVER_PORT: 443,
            },
        )
        self.memory_exporter.clear()

        # Test global endpoint
        iam_global = self._make_client("iam")
        iam_global.list_users()
        self.assert_span(
            "IAM",
            "ListUsers",
            attributes={
                SpanAttributes.SERVER_ADDRESS: "iam.amazonaws.com",
                SpanAttributes.SERVER_PORT: 443,
                CLOUD_REGION: "aws-global",
            },
        )

    @mock_aws
    def test_server_attributes_with_custom_endpoint(self):
        with patch.dict(
            os.environ,
            {"MOTO_S3_CUSTOM_ENDPOINTS": "https://proxy.amazon.org:2025"},
        ):
            s3 = self.session.create_client(
                "s3",
                region_name=self.region,
                endpoint_url="https://proxy.amazon.org:2025",
            )

            s3.list_buckets()

            self.assert_span(
                "S3",
                "ListBuckets",
                attributes={
                    SpanAttributes.SERVER_ADDRESS: "proxy.amazon.org",
                    SpanAttributes.SERVER_PORT: 2025,
                },
            )
