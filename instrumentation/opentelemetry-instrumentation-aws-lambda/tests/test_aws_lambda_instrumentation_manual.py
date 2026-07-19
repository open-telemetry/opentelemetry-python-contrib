# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-lines

import logging
import os
from copy import deepcopy
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
    _default_event_context_extractor,
)
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.aws.aws_xray_propagator import (
    TRACE_ID_FIRST_PART_LENGTH,
    TRACE_ID_VERSION,
)
from opentelemetry.semconv._incubating.attributes.cloud_attributes import (
    CLOUD_ACCOUNT_ID,
    CLOUD_RESOURCE_ID,
)
from opentelemetry.semconv._incubating.attributes.faas_attributes import (
    FAAS_INVOCATION_ID,
    FAAS_TRIGGER,
    FaasTriggerValues,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_ROUTE,
    HTTP_SCHEME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_USER_AGENT,
)
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_BATCH_MESSAGE_COUNT,
    MESSAGING_DESTINATION_NAME,
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION_TYPE,
    MESSAGING_SYSTEM,
    MessagingOperationTypeValues,
    MessagingSystemValues,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_HOST_NAME,
)
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
from .mocks.sqs_event import (
    MOCK_LAMBDA_SQS_BATCH_EVENT,
    MOCK_LAMBDA_SQS_BATCH_EVENT_PARTIAL_CONTEXT,
    MOCK_LAMBDA_SQS_EVENT,
    MOCK_LAMBDA_SQS_EVENT_ABSENT_MESSAGE_ATTRS,
    MOCK_LAMBDA_SQS_EVENT_ATTR_NOT_DICT,
    MOCK_LAMBDA_SQS_EVENT_INVALID_TRACEPARENT,
    MOCK_LAMBDA_SQS_EVENT_MISSING_ARN,
    MOCK_LAMBDA_SQS_EVENT_MISSING_STRING_VALUE,
    MOCK_LAMBDA_SQS_EVENT_NULL_MESSAGE_ATTRS,
    MOCK_LAMBDA_SQS_EVENT_SHORT_ARN,
    MOCK_LAMBDA_SQS_EVENT_UPPERCASE_ATTRS,
    MOCK_LAMBDA_SQS_EVENT_WITH_TRACE_CONTEXT,
    MOCK_MALFORMED_SQS_EVENT_EMPTY_RECORDS,
    MOCK_MALFORMED_SQS_EVENT_NO_RECORDS_KEY,
    MOCK_MALFORMED_SQS_EVENT_RECORDS_NOT_LIST,
    MOCK_MALFORMED_SQS_EVENT_WRONG_SOURCE,
)


class MockLambdaContext:
    def __init__(self, function_name, aws_request_id, invoked_function_arn):
        self.function_name = function_name
        self.invoked_function_arn = invoked_function_arn
        self.aws_request_id = aws_request_id


MOCK_LAMBDA_CONTEXT = MockLambdaContext(
    function_name="myfunction",
    aws_request_id="mock_aws_request_id",
    invoked_function_arn="arn:aws:lambda:us-east-1:123456:function:myfunction:myalias",
)

MOCK_LAMBDA_CONTEXT_ATTRIBUTES = {
    CLOUD_RESOURCE_ID: ":".join(
        MOCK_LAMBDA_CONTEXT.invoked_function_arn.split(":")[:7]
    ),
    FAAS_INVOCATION_ID: MOCK_LAMBDA_CONTEXT.aws_request_id,
    CLOUD_ACCOUNT_ID: MOCK_LAMBDA_CONTEXT.invoked_function_arn.split(":")[4],
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


def mock_execute_lambda(event=None, context=None):
    """Mocks the AWS Lambda execution.

    NOTE: We don't use `moto`'s `mock_lambda` because we are not instrumenting
    calls to AWS Lambda using the AWS SDK. Instead, we are instrumenting AWS
    Lambda itself.

    See more:
    https://docs.aws.amazon.com/lambda/latest/dg/runtimes-modify.html#runtime-wrapper

    Args:
        event: The Lambda event which may or may not be used by instrumentation.
        context: The AWS Lambda context to call the handler with
    """

    module_name, handler_name = os.environ[_HANDLER].rsplit(".", 1)
    handler_module = import_module(module_name.replace("/", "."))
    return getattr(handler_module, handler_name)(
        event, context or MOCK_LAMBDA_CONTEXT
    )


class TestAwsLambdaInstrumentorBase(TestBase):
    """AWS Lambda Instrumentation Testsuite"""

    def setUp(self):
        super().setUp()
        self.common_env_patch = mock.patch.dict(
            "os.environ",
            {
                _HANDLER: "tests.mocks.lambda_function.handler",
                "AWS_LAMBDA_FUNCTION_NAME": "mylambda",
            },
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
    def test_default_event_context_extractor_does_not_log_for_missing_headers(
        self,
    ):
        with mock.patch(
            "opentelemetry.instrumentation.aws_lambda.logger.debug"
        ) as debug_mock:
            _default_event_context_extractor({})

        self.assertEqual(debug_mock.call_count, 0)

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
        self.assertEqual(span.name, MOCK_LAMBDA_CONTEXT.function_name)
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
            TestCase(
                name="case_insensitive_headers_uppercase",
                custom_extractor=None,
                context={
                    "headers": {
                        TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME.upper(): MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                        TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME.upper(): f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
            ),
            TestCase(
                name="case_insensitive_headers_mixedcase",
                custom_extractor=None,
                context={
                    "headers": {
                        "TraceParent": MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                        "tRaCeStAtE": f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                    }
                },
                expected_traceid=MOCK_W3C_TRACE_ID,
                expected_parentid=MOCK_W3C_PARENT_SPAN_ID,
                expected_trace_state_len=3,
                expected_state_value=MOCK_W3C_TRACE_STATE_VALUE,
                xray_traceid=MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
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

    def test_api_gateway_v1_attributes_case_insensitivity(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(
            {
                "httpMethod": "GET",
                "headers": {
                    "user-agent": "lowercase-agent",
                    "host": "lowercase-host",
                    "x-forwarded-proto": "http",
                },
                "resource": "/test",
                "requestContext": {
                    "version": "1.0",
                },
            }
        )

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.attributes.get(HTTP_USER_AGENT), "lowercase-agent"
        )
        self.assertEqual(span.attributes.get(NET_HOST_NAME), "lowercase-host")
        self.assertEqual(span.attributes.get(HTTP_SCHEME), "http")

        self.memory_exporter.clear()

        mock_execute_lambda(
            {
                "httpMethod": "GET",
                "headers": {
                    "uSeR-aGeNt": "mixed-agent",
                    "hOsT": "mixed-host",
                    "X-fOrWaRdEd-PrOtO": "https",
                },
                "resource": "/test",
                "requestContext": {
                    "version": "1.0",
                },
            }
        )

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.attributes.get(HTTP_USER_AGENT), "mixed-agent")
        self.assertEqual(span.attributes.get(NET_HOST_NAME), "mixed-host")
        self.assertEqual(span.attributes.get(HTTP_SCHEME), "https")

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
        # SQS produces 2 spans (SERVER invocation + CONSUMER process), others produce 1 each
        assert len(spans) == 5

        server_spans = [s for s in spans if s.kind == SpanKind.SERVER]
        consumer_spans = [s for s in spans if s.kind == SpanKind.CONSUMER]
        assert len(server_spans) == 4
        assert len(consumer_spans) == 1

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

    @mock.patch("opentelemetry.instrumentation.aws_lambda.logger")
    def test_lambda_handles_should_do_nothing_when_aws_lambda_environment_variables_not_present(
        self, logger_mock
    ):
        exc_env_patch = mock.patch.dict(
            "os.environ",
            {_HANDLER: "tests.mocks.lambda_function.handler"},
            clear=True,
        )
        exc_env_patch.start()
        AwsLambdaInstrumentor().instrument()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        exc_env_patch.stop()

        logger_mock.warnings.assert_not_called()

    def test_lambda_handles_should_warn_when_handler_environment_variable_not_present(
        self,
    ):
        exc_env_patch = mock.patch.dict(
            "os.environ",
            {"AWS_LAMBDA_FUNCTION_NAME": "mylambda"},
            clear=True,
        )
        exc_env_patch.start()
        with self.assertLogs(level=logging.WARNING) as warning:
            AwsLambdaInstrumentor().instrument()
        self.assertEqual(len(warning.records), 1)
        self.assertIn(
            "This instrumentation requires the OpenTelemetry Lambda extension installed",
            warning.records[0].message,
        )

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


# pylint: disable-next=too-many-public-methods
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
                NET_HOST_NAME: "0123456789.execute-api.us-east-1.amazonaws.com",
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
                HTTP_SCHEME: "https",
                HTTP_USER_AGENT: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6)",
                NET_HOST_NAME: "lambda-846800462-us-east-2.elb.amazonaws.com",
            },
        )

    def test_alb_mixed_header_event_sets_attributes(self):
        AwsLambdaInstrumentor().instrument()

        event = deepcopy(MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT)
        event["headers"] = {"accept": "text/html,application/xhtml+xml"}

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_SCHEME: "https",
                HTTP_USER_AGENT: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6)",
                NET_HOST_NAME: "lambda-846800462-us-east-2.elb.amazonaws.com",
            },
        )

    def test_alb_mixed_header_event_prefers_multi_value_headers(self):
        AwsLambdaInstrumentor().instrument()

        event = deepcopy(MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT)
        event["headers"] = {
            "host": "wrong.example.com",
            "user-agent": "wrong-agent",
            "x-forwarded-proto": "http",
        }

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_SCHEME: "https",
                HTTP_USER_AGENT: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6)",
                NET_HOST_NAME: "lambda-846800462-us-east-2.elb.amazonaws.com",
            },
        )

    @mock.patch.dict(
        "os.environ",
        {
            _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
            OTEL_PROPAGATORS: "tracecontext",
        },
    )
    def test_alb_multi_value_header_event_extracts_parent_context(self):
        reload(propagate)

        AwsLambdaInstrumentor().instrument()

        event = deepcopy(MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT)
        event["multiValueHeaders"][
            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME
        ] = [MOCK_W3C_TRACE_CONTEXT_SAMPLED]

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.get_span_context().trace_id, MOCK_W3C_TRACE_ID)

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_W3C_PARENT_SPAN_ID)
        self.assertTrue(parent_context.is_remote)

    @mock.patch.dict(
        "os.environ",
        {
            _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
            OTEL_PROPAGATORS: "tracecontext",
        },
    )
    def test_alb_mixed_header_event_extracts_parent_context(self):
        reload(propagate)

        AwsLambdaInstrumentor().instrument()

        event = deepcopy(MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT)
        event["headers"] = {"accept": "text/html,application/xhtml+xml"}
        event["multiValueHeaders"][
            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME
        ] = [MOCK_W3C_TRACE_CONTEXT_SAMPLED]

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.get_span_context().trace_id, MOCK_W3C_TRACE_ID)

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_W3C_PARENT_SPAN_ID)
        self.assertTrue(parent_context.is_remote)

    @mock.patch.dict(
        "os.environ",
        {
            _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
            OTEL_PROPAGATORS: "tracecontext",
        },
    )
    def test_alb_mixed_header_event_prefers_multi_value_traceparent(self):
        reload(propagate)

        AwsLambdaInstrumentor().instrument()

        event = deepcopy(MOCK_LAMBDA_ALB_MULTI_VALUE_HEADER_EVENT)
        event["headers"] = {
            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: (
                "00-11111111111111111111111111111111-2222222222222222-01"
            )
        }
        event["multiValueHeaders"][
            TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME
        ] = [MOCK_W3C_TRACE_CONTEXT_SAMPLED]

        mock_execute_lambda(event)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span, *_ = spans
        self.assertEqual(span.get_span_context().trace_id, MOCK_W3C_TRACE_ID)

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_W3C_PARENT_SPAN_ID)
        self.assertTrue(parent_context.is_remote)

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
        # SQS produces two spans: inner CONSUMER first, outer SERVER second
        self.assertEqual(len(spans), 2)

        consumer_span, server_span, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(server_span.kind, SpanKind.SERVER)

        self.assertSpanHasAttributes(
            server_span,
            {
                **MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
                FAAS_TRIGGER: FaasTriggerValues.PUBSUB.value,
            },
        )
        self.assertSpanHasAttributes(
            consumer_span,
            {
                MESSAGING_SYSTEM: MessagingSystemValues.AWS_SQS.value,
                MESSAGING_DESTINATION_NAME: "my-queue",
                MESSAGING_OPERATION_TYPE: MessagingOperationTypeValues.PROCESS.value,
            },
        )
        self.assertEqual(consumer_span.name, "process my-queue")
        # Single record event should have no batch count attribute
        self.assertNotIn(
            MESSAGING_BATCH_MESSAGE_COUNT, consumer_span.attributes
        )
        # No span links when messageAttributes is empty
        self.assertEqual(len(consumer_span.links), 0)
        # CONSUMER span is a child of the SERVER span
        self.assertEqual(
            consumer_span.parent.span_id,
            server_span.get_span_context().span_id,
        )

    def test_sqs_event_span_links(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_WITH_TRACE_CONTEXT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        consumer_span, _server_span, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)

        # Exactly one link corresponding to the producer's trace context
        self.assertEqual(len(consumer_span.links), 1)
        link = consumer_span.links[0]
        self.assertEqual(
            link.context.trace_id,
            0x5CE0E9A56015FEC5AADFA328AE398115,
        )
        self.assertEqual(
            link.context.span_id,
            0xAB54A98CEB1F0AD2,
        )
        self.assertEqual(
            link.attributes.get(MESSAGING_MESSAGE_ID),
            "059f36b4-87a3-44ab-83d2-661975830a7d",
        )

    def test_sqs_batch_event_attributes(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_BATCH_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        consumer_span, _server_span, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)

        self.assertEqual(
            consumer_span.attributes.get(MESSAGING_BATCH_MESSAGE_COUNT), 2
        )
        self.assertEqual(len(consumer_span.links), 2)

    def test_sqs_message_attributes_case_insensitive(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_UPPERCASE_ATTRS)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        consumer_span, _server_span, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)

        # Uppercase TRACEPARENT key should still produce a span link
        self.assertEqual(len(consumer_span.links), 1)
        link = consumer_span.links[0]
        self.assertEqual(
            link.context.trace_id,
            0x5CE0E9A56015FEC5AADFA328AE398115,
        )
        self.assertEqual(
            link.context.span_id,
            0xAB54A98CEB1F0AD2,
        )

    @mock.patch.dict(
        "os.environ", {_HANDLER: "tests.mocks.lambda_function.handler_exc"}
    )
    def test_sqs_event_exception(self):
        AwsLambdaInstrumentor().instrument()

        with self.assertRaises(Exception):
            mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        consumer_span, server_span, *_ = spans
        self.assertEqual(consumer_span.status.status_code, StatusCode.ERROR)
        self.assertEqual(server_span.status.status_code, StatusCode.ERROR)
        # Both spans should have an exception event recorded
        self.assertTrue(
            any(e.name == "exception" for e in consumer_span.events)
        )
        self.assertTrue(any(e.name == "exception" for e in server_span.events))

    def test_sqs_event_null_message_attrs(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_NULL_MESSAGE_ATTRS)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(len(consumer_span.links), 0)

    def test_sqs_event_absent_message_attrs(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_ABSENT_MESSAGE_ATTRS)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(len(consumer_span.links), 0)

    def test_sqs_batch_event_partial_context(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_BATCH_EVENT_PARTIAL_CONTEXT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        # Record 1 has no context records 2 and 3 do
        self.assertEqual(len(consumer_span.links), 2)
        trace_ids = {link.context.trace_id for link in consumer_span.links}
        self.assertIn(0xAABBCCDDEEFF00112233445566778899, trace_ids)
        self.assertIn(0xCAFEBABE12345678CAFEBABE12345678, trace_ids)

    def test_malformed_sqs_event_empty_records(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_MALFORMED_SQS_EVENT_EMPTY_RECORDS)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.SERVER)

    def test_malformed_sqs_event_records_not_list(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_MALFORMED_SQS_EVENT_RECORDS_NOT_LIST)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.SERVER)

    def test_malformed_sqs_event_wrong_source(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_MALFORMED_SQS_EVENT_WRONG_SOURCE)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.SERVER)

    def test_malformed_sqs_event_no_records_key(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_MALFORMED_SQS_EVENT_NO_RECORDS_KEY)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.SERVER)

    def test_sqs_event_invalid_traceparent(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_INVALID_TRACEPARENT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(len(consumer_span.links), 0)

    def test_sqs_event_attr_not_dict(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_ATTR_NOT_DICT)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(len(consumer_span.links), 0)

    def test_sqs_event_missing_string_value(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_MISSING_STRING_VALUE)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(len(consumer_span.links), 0)

    def test_sqs_event_missing_arn_span_name(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_MISSING_ARN)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(consumer_span.name, "process")

    def test_sqs_event_short_arn_span_name(self):
        AwsLambdaInstrumentor().instrument()

        mock_execute_lambda(MOCK_LAMBDA_SQS_EVENT_SHORT_ARN)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        consumer_span, _, *_ = spans
        self.assertEqual(consumer_span.kind, SpanKind.CONSUMER)
        self.assertEqual(consumer_span.name, "process bad-arn")

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
