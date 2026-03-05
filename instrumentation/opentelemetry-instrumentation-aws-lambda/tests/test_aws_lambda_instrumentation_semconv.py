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

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.aws_lambda import (
    _HANDLER,
    AwsLambdaInstrumentor,
)
from opentelemetry.semconv._incubating.attributes.faas_attributes import (
    FAAS_TRIGGER,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    HTTP_ROUTE,
    HTTP_SCHEME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_USER_AGENT,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_HOST_NAME,
)
from opentelemetry.semconv._incubating.attributes.server_attributes import (
    SERVER_ADDRESS,
)
from opentelemetry.semconv._incubating.attributes.url_attributes import (
    URL_PATH,
    URL_QUERY,
    URL_SCHEME,
)
from opentelemetry.semconv._incubating.attributes.user_agent_attributes import (
    USER_AGENT_ORIGINAL,
)
from opentelemetry.trace import SpanKind

from .mocks.alb_conventional_headers_event import MOCK_LAMBDA_ALB_EVENT
from .mocks.api_gateway_http_api_event import (
    MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT,
)
from .mocks.api_gateway_proxy_event import MOCK_LAMBDA_API_GATEWAY_PROXY_EVENT
from .mocks.dynamo_db_event import MOCK_LAMBDA_DYNAMO_DB_EVENT
from .mocks.sqs_event import MOCK_LAMBDA_SQS_EVENT
from .test_aws_lambda_instrumentation_base import (
    MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
    TestAwsLambdaInstrumentorBase,
    mock_execute_lambda,
)


class TestAwsLambdaInstrumentorNewSemconv(TestAwsLambdaInstrumentorBase):
    """Test AWS Lambda Instrumentation with new semantic conventions"""

    def setUp(self):
        super().setUp()
        test_name = ""
        if hasattr(self, "_testMethodName"):
            test_name = self._testMethodName
        sem_conv_mode = "default"
        if "new_semconv" in test_name:
            sem_conv_mode = "http"
        elif "both_semconv" in test_name:
            sem_conv_mode = "http/dup"

        self.common_env_patch = mock.patch.dict(
            "os.environ",
            {
                _HANDLER: "tests.mocks.lambda_function.rest_api_handler",
                "AWS_LAMBDA_FUNCTION_NAME": "mylambda",
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.common_env_patch.start()

    def tearDown(self):
        super().tearDown()
        self.common_env_patch.stop()
        AwsLambdaInstrumentor().uninstrument()

    def test_api_gateway_proxy_event_sets_attributes_new_semconv(self):
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
                HTTP_REQUEST_METHOD: "POST",
                HTTP_RESPONSE_STATUS_CODE: 200,
                URL_PATH: "/{proxy+}",
                URL_QUERY: "foo=bar",
                SERVER_ADDRESS: "1234567890.execute-api.us-east-1.amazonaws.com",
                USER_AGENT_ORIGINAL: "Custom User Agent String",
                URL_SCHEME: "https",
            },
        )
        # Ensure old attributes are not present
        self.assertNotIn(HTTP_METHOD, span.attributes)
        self.assertNotIn(HTTP_TARGET, span.attributes)
        self.assertNotIn(NET_HOST_NAME, span.attributes)
        self.assertNotIn(HTTP_USER_AGENT, span.attributes)
        self.assertNotIn(HTTP_SCHEME, span.attributes)
        self.assertNotIn(HTTP_STATUS_CODE, span.attributes)

    def test_api_gateway_proxy_event_sets_attributes_both_semconv(self):
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
        # New semconv attributes
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_STATUS_CODE: 200,
                HTTP_RESPONSE_STATUS_CODE: 200,
                HTTP_REQUEST_METHOD: "POST",
                HTTP_USER_AGENT: "Custom User Agent String",
                SERVER_ADDRESS: "1234567890.execute-api.us-east-1.amazonaws.com",
                URL_PATH: "/{proxy+}",
                URL_QUERY: "foo=bar",
                URL_SCHEME: "https",
            },
        )
        # Old semconv attributes should also be present
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_METHOD: "POST",
                HTTP_TARGET: "/{proxy+}?foo=bar",
                NET_HOST_NAME: "1234567890.execute-api.us-east-1.amazonaws.com",
                HTTP_USER_AGENT: "Custom User Agent String",
                HTTP_SCHEME: "https",
                USER_AGENT_ORIGINAL: "Custom User Agent String",
            },
        )

    def test_api_gateway_http_api_proxy_event_sets_attributes_new_semconv(
        self,
    ):
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
                HTTP_REQUEST_METHOD: "POST",
                HTTP_ROUTE: "/path/to/resource",
                URL_PATH: "/path/to/resource",
                URL_QUERY: "parameter1=value1&parameter1=value2&parameter2=value",
                SERVER_ADDRESS: "id.execute-api.us-east-1.amazonaws.com",
                USER_AGENT_ORIGINAL: "agent",
            },
        )
        # Ensure old attributes are not present
        self.assertNotIn(HTTP_METHOD, span.attributes)
        self.assertNotIn(HTTP_TARGET, span.attributes)
        self.assertNotIn(NET_HOST_NAME, span.attributes)
        self.assertNotIn(HTTP_USER_AGENT, span.attributes)

    def test_api_gateway_http_api_proxy_event_sets_attributes_both_semconv(
        self,
    ):
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
        # New semconv attributes
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_REQUEST_METHOD: "POST",
                HTTP_ROUTE: "/path/to/resource",
                URL_PATH: "/path/to/resource",
                URL_QUERY: "parameter1=value1&parameter1=value2&parameter2=value",
                SERVER_ADDRESS: "id.execute-api.us-east-1.amazonaws.com",
                USER_AGENT_ORIGINAL: "agent",
            },
        )
        # Old semconv attributes should also be present
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_METHOD: "POST",
                HTTP_TARGET: "/path/to/resource?parameter1=value1&parameter1=value2&parameter2=value",
                NET_HOST_NAME: "id.execute-api.us-east-1.amazonaws.com",
                HTTP_USER_AGENT: "agent",
            },
        )

    def test_alb_event_sets_attributes_new_semconv(self):
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
                HTTP_REQUEST_METHOD: "GET",
                HTTP_RESPONSE_STATUS_CODE: 200,
            },
        )
        # Ensure old HTTP_METHOD attribute is not present
        self.assertNotIn(HTTP_METHOD, span.attributes)

    def test_alb_event_sets_attributes_both_semconv(self):
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
        # Both old and new attributes should be present
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_REQUEST_METHOD: "GET",
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 200,
                HTTP_RESPONSE_STATUS_CODE: 200,
            },
        )

    def test_api_gateway_without_optional_fields_new_semconv(self):
        """Test API Gateway event without optional fields like User-Agent"""
        event = {
            "requestContext": {
                "http": {
                    "method": "GET",
                    "path": "/test",
                }
            },
            "headers": {},
        }

        AwsLambdaInstrumentor().instrument()
        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_REQUEST_METHOD: "GET",
            },
        )
        # Ensure old attribute is not present
        self.assertNotIn(HTTP_METHOD, span.attributes)
        # Optional attributes should not be present
        self.assertNotIn(USER_AGENT_ORIGINAL, span.attributes)
        self.assertNotIn(HTTP_USER_AGENT, span.attributes)

    def test_api_gateway_v1_with_scheme_and_host_new_semconv(self):
        """Test API Gateway v1 event with X-Forwarded-Proto and Host headers"""
        event = {
            "requestContext": {
                "accountId": "123456789012",
                "resourceId": "123456",
                "stage": "prod",
            },
            "httpMethod": "PUT",
            "resource": "/users/{id}",
            "headers": {
                "X-Forwarded-Proto": "https",
                "Host": "api.example.com",
                "User-Agent": "Mozilla/5.0",
            },
            "queryStringParameters": {"filter": "active"},
        }

        AwsLambdaInstrumentor().instrument()
        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertSpanHasAttributes(
            span,
            {
                FAAS_TRIGGER: "http",
                HTTP_REQUEST_METHOD: "PUT",
                HTTP_ROUTE: "/users/{id}",
                URL_PATH: "/users/{id}",
                URL_QUERY: "filter=active",
                URL_SCHEME: "https",
                SERVER_ADDRESS: "api.example.com",
                USER_AGENT_ORIGINAL: "Mozilla/5.0",
            },
        )
        # Ensure old attributes are not present
        self.assertNotIn(HTTP_METHOD, span.attributes)
        self.assertNotIn(HTTP_TARGET, span.attributes)
        self.assertNotIn(HTTP_SCHEME, span.attributes)
        self.assertNotIn(NET_HOST_NAME, span.attributes)
        self.assertNotIn(HTTP_USER_AGENT, span.attributes)

    def test_api_gateway_v1_with_scheme_and_host_both_semconv(self):
        """Test API Gateway v1 event with both old and new semconv"""
        event = {
            "requestContext": {
                "accountId": "123456789012",
                "resourceId": "123456",
                "stage": "prod",
            },
            "httpMethod": "PUT",
            "resource": "/users/{id}",
            "headers": {
                "X-Forwarded-Proto": "https",
                "Host": "api.example.com",
                "User-Agent": "Mozilla/5.0",
            },
            "queryStringParameters": {"filter": "active"},
        }

        AwsLambdaInstrumentor().instrument()
        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        # New semconv attributes
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_REQUEST_METHOD: "PUT",
                HTTP_METHOD: "PUT",
                HTTP_SCHEME: "https",
                URL_SCHEME: "https",
                HTTP_STATUS_CODE: 200,
                HTTP_RESPONSE_STATUS_CODE: 200,
                HTTP_TARGET: "/users/{id}?filter=active",
                HTTP_USER_AGENT: "Mozilla/5.0",
                USER_AGENT_ORIGINAL: "Mozilla/5.0",
                NET_HOST_NAME: "api.example.com",
                SERVER_ADDRESS: "api.example.com",
                URL_PATH: "/users/{id}",
                URL_QUERY: "filter=active",
            },
        )
        # Old semconv attributes
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_METHOD: "PUT",
                HTTP_TARGET: "/users/{id}?filter=active",
                HTTP_SCHEME: "https",
                NET_HOST_NAME: "api.example.com",
                HTTP_USER_AGENT: "Mozilla/5.0",
            },
        )

    def test_api_gateway_v2_without_query_string_new_semconv(self):
        """Test API Gateway v2 event without query string"""
        event = {
            "requestContext": {
                "http": {
                    "method": "DELETE",
                    "path": "/items/123",
                    "userAgent": "TestAgent/1.0",
                },
                "domainName": "api.test.com",
            },
            "version": "2.0",
        }

        AwsLambdaInstrumentor().instrument()
        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_REQUEST_METHOD: "DELETE",
                URL_PATH: "/items/123",
                SERVER_ADDRESS: "api.test.com",
                USER_AGENT_ORIGINAL: "TestAgent/1.0",
                HTTP_RESPONSE_STATUS_CODE: 200,
            },
        )
        # URL_QUERY should not be present when there's no query string
        self.assertNotIn(URL_QUERY, span.attributes)
        # Ensure old attributes are not present
        self.assertNotIn(HTTP_METHOD, span.attributes)
        self.assertNotIn(HTTP_TARGET, span.attributes)

    def test_status_code_response_new_semconv(self):
        """Test that HTTP status code is correctly set with new semconv"""
        AwsLambdaInstrumentor().instrument()

        # Create event with request context to trigger HTTP attribute extraction
        event = MOCK_LAMBDA_API_GATEWAY_PROXY_EVENT.copy()

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_RESPONSE_STATUS_CODE: 200,
            },
        )
        # Ensure old attribute is not present
        self.assertNotIn(HTTP_STATUS_CODE, span.attributes)

    def test_status_code_response_both_semconv(self):
        AwsLambdaInstrumentor().instrument()

        event = MOCK_LAMBDA_API_GATEWAY_PROXY_EVENT.copy()

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        # Both old and new attributes should be present
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_RESPONSE_STATUS_CODE: 200,
                HTTP_STATUS_CODE: 200,
            },
        )

    def test_non_http_trigger_unaffected_by_semconv_new(self):
        """Test that non-HTTP triggers are unaffected by semconv changes"""
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
        # Should not have any HTTP attributes
        self.assertNotIn(HTTP_REQUEST_METHOD, span.attributes)
        self.assertNotIn(HTTP_METHOD, span.attributes)
        self.assertNotIn(URL_PATH, span.attributes)
        self.assertNotIn(HTTP_TARGET, span.attributes)

    def test_non_http_trigger_unaffected_by_semconv_both(self):
        """Test that non-HTTP triggers work correctly with both semconv mode"""
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
        # Should not have any HTTP attributes
        self.assertNotIn(HTTP_REQUEST_METHOD, span.attributes)
        self.assertNotIn(HTTP_METHOD, span.attributes)
        self.assertNotIn(URL_PATH, span.attributes)
        self.assertNotIn(HTTP_TARGET, span.attributes)
