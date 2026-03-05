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

from unittest import mock

from opentelemetry.instrumentation.aws_lambda import (
    _HANDLER,
    AwsLambdaInstrumentor,
)
from opentelemetry.semconv._incubating.attributes.faas_attributes import (
    FAAS_TRIGGER,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_ROUTE,
    HTTP_SCHEME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_USER_AGENT,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_HOST_NAME,
)
from opentelemetry.trace import SpanKind, StatusCode

from .mocks.alb_conventional_headers_event import MOCK_LAMBDA_ALB_EVENT
from .mocks.alb_multi_value_headers_event import (
    MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT,
)
from .mocks.api_gateway_http_api_event import (
    MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT,
)
from .mocks.api_gateway_proxy_event import MOCK_LAMBDA_API_GATEWAY_PROXY_EVENT
from .mocks.dynamo_db_event import MOCK_LAMBDA_DYNAMO_DB_EVENT
from .mocks.s3_event import MOCK_LAMBDA_S3_EVENT
from .mocks.sns_event import MOCK_LAMBDA_SNS_EVENT
from .mocks.sqs_event import MOCK_LAMBDA_SQS_EVENT
from .test_aws_lambda_instrumentation_base import (
    MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
    TestAwsLambdaInstrumentorBase,
    mock_execute_lambda,
)


class TestAwsLambdaInstrumentorMocks(TestAwsLambdaInstrumentorBase):
    def test_api_gateway_proxy_event_sets_attributes(self):
        handler_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests.mocks.lambda_function.rest_api_handler"},
        )
        handler_patch.start()

        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_API_GATEWAY_PROXY_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_METHOD: "POST",
                HTTP_ROUTE: "/{proxy+}",
                HTTP_TARGET: "/{proxy+}?foo=bar",
                NET_HOST_NAME: "1234567890.execute-api.us-east-1.amazonaws.com",
                HTTP_USER_AGENT: "Custom User Agent String",
                HTTP_SCHEME: "https",
                HTTP_STATUS_CODE: 200,
            },
        )

    def test_api_gateway_http_api_proxy_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_METHOD: "POST",
                HTTP_ROUTE: "/path/to/resource",
                HTTP_TARGET: "/path/to/resource?parameter1=value1&parameter1=value2&parameter2=value",
                NET_HOST_NAME: "id.execute-api.us-east-1.amazonaws.com",
                HTTP_USER_AGENT: "agent",
            },
        )

    def test_alb_conventional_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_ALB_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_METHOD: "GET",
            },
        )

    def test_alb_multi_value_header_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_METHOD: "GET",
            },
        )

    def test_dynamo_db_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_DYNAMO_DB_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

    def test_s3_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_S3_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

    def test_sns_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SNS_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

    def test_sqs_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

    def test_slash_delimited_handler_path(self):
        """Test that slash-delimited handler paths work correctly.

        AWS Lambda accepts both slash-delimited (python/functions/api.handler)
        and dot-delimited (python.functions.api.handler) handler paths.
        This test ensures the instrumentation handles both formats.
        """
        # Test slash-delimited format
        slash_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests/mocks/lambda_function.handler"},
        )
        slash_env_patch.start()
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertSpanHasAttributes(
            spans[0],
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

        slash_env_patch.stop()
        AwsLambdaInstrumentor().uninstrument()
        self.memory_exporter.clear()

        # Test dot-delimited format (should still work)
        dot_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests.mocks.lambda_function.handler"},
        )
        dot_env_patch.start()
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertSpanHasAttributes(
            spans[0],
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

        dot_env_patch.stop()

    def test_lambda_handles_handler_exception_with_api_gateway_proxy_event(
        self,
    ):
        exc_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests.mocks.lambda_function.handler_exc"},
        )
        exc_env_patch.start()
        AwsLambdaInstrumentor().instrument()

        # instrumentor re-raises the exception
        with self.assertRaises(Exception):
            mock_execute_lambda(
                {"requestContext": {"http": {"method": "GET"}}}
            )

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(len(span.events), 1)

        event, *_ = span.events
        self.assertEqual(event.name, "exception")

        exc_env_patch.stop()
