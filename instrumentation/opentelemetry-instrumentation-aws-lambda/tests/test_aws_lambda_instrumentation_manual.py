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
import os
from dataclasses import dataclass
from importlib import import_module, reload
from typing import Any, Callable, Dict
from unittest import mock

from opentelemetry import propagate
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.environment_variables import OTEL_PROPAGATORS
from opentelemetry.instrumentation.aws_lambda import (
    _HANDLER,
    _X_AMZN_TRACE_ID,
    OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT,
    AwsLambdaInstrumentor,
)
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.aws.aws_xray_propagator import (
    TRACE_ID_FIRST_PART_LENGTH,
    TRACE_ID_VERSION,
)
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import NoOpTracerProvider, SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from opentelemetry.util._importlib_metadata import entry_points

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


class MockLambdaContext:
    def __init__(self, aws_request_id, invoked_function_arn):
        self.invoked_function_arn = invoked_function_arn
        self.aws_request_id = aws_request_id


MOCK_LAMBDA_CONTEXT = MockLambdaContext(
    aws_request_id="mock_aws_request_id",
    invoked_function_arn="arn:aws:lambda:us-east-1:123456:function:myfunction:myalias",
)

MOCK_LAMBDA_CONTEXT_ATTRIBUTES = {
    SpanAttributes.CLOUD_RESOURCE_ID: MOCK_LAMBDA_CONTEXT.invoked_function_arn,
    SpanAttributes.FAAS_INVOCATION_ID: MOCK_LAMBDA_CONTEXT.aws_request_id,
    ResourceAttributes.CLOUD_ACCOUNT_ID: MOCK_LAMBDA_CONTEXT.invoked_function_arn.split(
        ":"
    )[
        4
    ],
}

MOCK_XRAY_TRACE_ID = 0x5FB7331105E8BB83207FA31D4D9CDB4C
MOCK_XRAY_TRACE_ID_STR = f"{MOCK_XRAY_TRACE_ID:x}"
MOCK_XRAY_PARENT_SPAN_ID = 0x3328B8445A6DBAD2
MOCK_XRAY_TRACE_CONTEXT_COMMON = f"Root={TRACE_ID_VERSION}-{MOCK_XRAY_TRACE_ID_STR[:TRACE_ID_FIRST_PART_LENGTH]}-{MOCK_XRAY_TRACE_ID_STR[TRACE_ID_FIRST_PART_LENGTH:]};Parent={MOCK_XRAY_PARENT_SPAN_ID:x}"
MOCK_XRAY_TRACE_CONTEXT_SAMPLED = f"{MOCK_XRAY_TRACE_CONTEXT_COMMON};Sampled=1"
MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED = (
    f"{MOCK_XRAY_TRACE_CONTEXT_COMMON};Sampled=0"
)

# See more:
# https://www.w3.org/TR/trace-context/#examples-of-http-traceparent-headers

MOCK_W3C_TRACE_ID = 0x5CE0E9A56015FEC5AADFA328AE398115
MOCK_W3C_PARENT_SPAN_ID = 0xAB54A98CEB1F0AD2
MOCK_W3C_TRACE_CONTEXT_SAMPLED = (
    f"00-{MOCK_W3C_TRACE_ID:x}-{MOCK_W3C_PARENT_SPAN_ID:x}-01"
)

MOCK_W3C_TRACE_STATE_KEY = "vendor_specific_key"
MOCK_W3C_TRACE_STATE_VALUE = "test_value"

MOCK_W3C_BAGGAGE_KEY = "baggage_key"
MOCK_W3C_BAGGAGE_VALUE = "baggage_value"


def mock_execute_lambda(event=None):
    """Mocks the AWS Lambda execution.

    NOTE: We don't use `moto`'s `mock_lambda` because we are not instrumenting
    calls to AWS Lambda using the AWS SDK. Instead, we are instrumenting AWS
    Lambda itself.

    See more:
    https://docs.aws.amazon.com/lambda/latest/dg/runtimes-modify.html#runtime-wrapper

    Args:
        event: The Lambda event which may or may not be used by instrumentation.
    """

    module_name, handler_name = os.environ[_HANDLER].rsplit(".", 1)
    handler_module = import_module(module_name.replace("/", "."))
    return getattr(handler_module, handler_name)(event, MOCK_LAMBDA_CONTEXT)


class TestAwsLambdaInstrumentorBase(TestBase):
    """AWS Lambda Instrumentation Testsuite"""

    def setUp(self):
        super().setUp()
        self.common_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests.mocks.lambda_function.handler"},
        )
        self.common_env_patch.start()

        # NOTE: Whether AwsLambdaInstrumentor().instrument() is run is decided
        # by each test case. It depends on if the test is for auto or manual
        # instrumentation.

    def tearDown(self):
        super().tearDown()
        self.common_env_patch.stop()
        AwsLambdaInstrumentor().uninstrument()


class TestAwsLambdaInstrumentor(TestAwsLambdaInstrumentorBase):
    def test_active_tracing(self):
        test_env_patch = mock.patch.dict(
            "os.environ",
            {
                **os.environ,
                # Using Active tracing
                OTEL_PROPAGATORS: "xray-lambda",
                _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_SAMPLED,
            },
        )

        test_env_patch.start()
        reload(propagate)

        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda()

        spans = self.memory_exporter.get_finished_spans()

        assert spans

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, os.environ[_HANDLER])
        self.assertEqual(span.get_span_context().trace_id, MOCK_XRAY_TRACE_ID)
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_XRAY_PARENT_SPAN_ID)
        self.assertTrue(parent_context.is_remote)

        test_env_patch.stop()

    def test_parent_context_from_lambda_event(self):
        @dataclass
        class TestCase:
            name: str
            custom_extractor: Callable[[Any], None]
            context: Dict
            expected_traceid: int
            expected_parentid: int
            xray_traceid: str
            expected_state_value: str = None
            expected_trace_state_len: int = 0
            propagators: str = "tracecontext"
            expected_baggage: str = None
            disable_aws_context_propagation: bool = False
            disable_aws_context_propagation_envvar: str = ""

        def custom_event_context_extractor(lambda_event):
            return get_global_textmap().extract(lambda_event["foo"]["headers"])

        tests = [
            TestCase(
                name="no_custom_extractor",
                custom_extractor=None,
                context={
                    "headers": {
                        TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                        TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
            ),
            TestCase(
                name="custom_extractor_not_sampled_xray",
                custom_extractor=custom_event_context_extractor,
                context={
                    "foo": {
                        "headers": {
                            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                            TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                        }
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
            ),
            TestCase(
                name="custom_extractor_sampled_xray",
                custom_extractor=custom_event_context_extractor,
                context={
                    "foo": {
                        "headers": {
                            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                            TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                        }
                    }
                },
                expected_traceid=MOCK_XRAY_TRACE_ID,
                expected_parentid=MOCK_XRAY_PARENT_SPAN_ID,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_SAMPLED,
                propagators="xray-lambda",
            ),
            TestCase(
                name="custom_extractor_sampled_xray",
                custom_extractor=custom_event_context_extractor,
                context={
                    "foo": {
                        "headers": {
                            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                            TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                        }
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_SAMPLED,
            ),
            TestCase(
                name="no_custom_extractor_xray",
                custom_extractor=None,
                context={
                    "headers": {
                        TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                        TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_SAMPLED,
            ),
            TestCase(
                name="baggage_propagation",
                custom_extractor=None,
                context={
                    "headers": {
                        TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                        TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                        W3CBaggagePropagator._BAGGAGE_HEADER_NAME: f"{MOCK_W3C_BAGGAGE_KEY}={MOCK_W3C_BAGGAGE_VALUE}",
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
                expected_baggage=MOCK_W3C_BAGGAGE_VALUE,
                propagators="tracecontext,baggage",
            ),
        ]
        for test in tests:
            with self.subTest(test_name=test.name):
                test_env_patch = mock.patch.dict(
                    "os.environ",
                    {
                        **os.environ,
                        # NOT Active Tracing
                        _X_AMZN_TRACE_ID: test.xray_traceid,
                        OTEL_PROPAGATORS: test.propagators,
                    },
                )
                test_env_patch.start()
                reload(propagate)

                AwsLambdaInstrumentor().instrument(
                    event_context_extractor=test.custom_extractor,
                )

                mock_execute_lambda(test.context)

                spans = self.memory_exporter.get_finished_spans()
                assert spans
                self.assertEqual(len(spans), 1)
                span = spans[0]
                self.assertEqual(
                    span.get_span_context().trace_id, test.expected_traceid
                )

                parent_context = span.parent
                self.assertEqual(
                    parent_context.trace_id, span.get_span_context().trace_id
                )
                self.assertEqual(
                    parent_context.span_id, test.expected_parentid
                )
                self.assertEqual(
                    len(parent_context.trace_state),
                    test.expected_trace_state_len,
                )
                self.assertEqual(
                    parent_context.trace_state.get(MOCK_W3C_TRACE_STATE_KEY),
                    test.expected_state_value,
                )
                self.assertTrue(parent_context.is_remote)
                self.memory_exporter.clear()
                AwsLambdaInstrumentor().uninstrument()
                test_env_patch.stop()

    def test_lambda_no_error_with_invalid_flush_timeout(self):
        test_env_patch = mock.patch.dict(
            "os.environ",
            {
                **os.environ,
                # NOT Active Tracing
                _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
                # NOT using the X-Ray Propagator
                OTEL_PROPAGATORS: "tracecontext",
                OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT: "invalid-timeout-string",
            },
        )
        test_env_patch.start()

        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda()

        spans = self.memory_exporter.get_finished_spans()

        assert spans

        self.assertEqual(len(spans), 1)

        test_env_patch.stop()

    def test_lambda_handles_multiple_consumers(self):
        test_env_patch = mock.patch.dict(
            "os.environ",
            {
                **os.environ,
                # NOT Active Tracing
                _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
                # NOT using the X-Ray Propagator
                OTEL_PROPAGATORS: "tracecontext",
            },
        )
        test_env_patch.start()

        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda({"Records": [{"eventSource": "aws:sqs"}]})
        mock_execute_lambda({"Records": [{"eventSource": "aws:s3"}]})
        mock_execute_lambda({"Records": [{"EventSource": "aws:sns"}]})
        mock_execute_lambda({"Records": [{"eventSource": "aws:dynamodb"}]})

        spans = self.memory_exporter.get_finished_spans()

        assert spans
        assert len(spans) == 4

        for span in spans:
            assert span.kind == SpanKind.CONSUMER

        test_env_patch.stop()

    def test_lambda_handles_invalid_event_source(self):
        test_env_patch = mock.patch.dict(
            "os.environ",
            {
                **os.environ,
                # NOT Active Tracing
                _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
                # NOT using the X-Ray Propagator
                OTEL_PROPAGATORS: "tracecontext",
            },
        )
        test_env_patch.start()
        reload(propagate)

        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda({"Records": [{"eventSource": "invalid_source"}]})

        spans = self.memory_exporter.get_finished_spans()

        assert spans
        assert len(spans) == 1
        # Default to SERVER for unknown sources
        assert spans[0].kind == SpanKind.SERVER

        for span in spans:
            self.assertSpanHasAttributes(
                span,
                MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
            )

        test_env_patch.stop()

    def test_lambda_handles_list_event(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda([{"message": "test"}])

        spans = self.memory_exporter.get_finished_spans()

        assert spans

    def test_lambda_handles_handler_exception(self):
        exc_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests.mocks.lambda_function.handler_exc"},
        )
        exc_env_patch.start()
        AwsLambdaInstrumentor().instrument()
        # instrumentor re-raises the exception
        with self.assertRaises(Exception):
            mock_execute_lambda()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(len(span.events), 1)
        event = span.events[0]
        self.assertEqual(event.name, "exception")

        exc_env_patch.stop()

    def test_lambda_handles_should_do_nothing_when_environment_variables_not_present(
        self,
    ):
        exc_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: ""},
        )
        exc_env_patch.start()
        AwsLambdaInstrumentor().instrument()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        exc_env_patch.stop()

    def test_uninstrument(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        self.memory_exporter.clear()
        AwsLambdaInstrumentor().uninstrument()

        mock_execute_lambda(MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_no_op_tracer_provider(self):
        tracer_provider = NoOpTracerProvider()
        AwsLambdaInstrumentor().instrument(tracer_provider=tracer_provider)

        mock_execute_lambda(MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT)
        spans = self.memory_exporter.get_finished_spans()
        assert spans is not None
        self.assertEqual(len(spans), 0)

    def test_load_entry_point(self):
        self.assertIs(
            next(
                iter(
                    entry_points(
                        group="opentelemetry_instrumentor", name="aws-lambda"
                    )
                )
            ).load(),
            AwsLambdaInstrumentor,
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
                SpanAttributes.FAAS_TRIGGER: "http",
                SpanAttributes.HTTP_METHOD: "POST",
                SpanAttributes.HTTP_ROUTE: "/{proxy+}",
                SpanAttributes.HTTP_TARGET: "/{proxy+}?foo=bar",
                SpanAttributes.NET_HOST_NAME: "1234567890.execute-api.us-east-1.amazonaws.com",
                SpanAttributes.HTTP_USER_AGENT: "Custom User Agent String",
                SpanAttributes.HTTP_SCHEME: "https",
                SpanAttributes.HTTP_STATUS_CODE: 200,
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
                SpanAttributes.FAAS_TRIGGER: "http",
                SpanAttributes.HTTP_METHOD: "POST",
                SpanAttributes.HTTP_ROUTE: "/path/to/resource",
                SpanAttributes.HTTP_TARGET: "/path/to/resource?parameter1=value1&parameter1=value2&parameter2=value",
                SpanAttributes.NET_HOST_NAME: "id.execute-api.us-east-1.amazonaws.com",
                SpanAttributes.HTTP_USER_AGENT: "agent",
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
                SpanAttributes.FAAS_TRIGGER: "http",
                SpanAttributes.HTTP_METHOD: "GET",
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
                SpanAttributes.FAAS_TRIGGER: "http",
                SpanAttributes.HTTP_METHOD: "GET",
            },
        )

    def test_dynamo_db_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_DYNAMO_DB_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.CONSUMER)
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
        self.assertEqual(span.kind, SpanKind.CONSUMER)
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
        self.assertEqual(span.kind, SpanKind.CONSUMER)
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
        self.assertEqual(span.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            span,
            MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
        )

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
