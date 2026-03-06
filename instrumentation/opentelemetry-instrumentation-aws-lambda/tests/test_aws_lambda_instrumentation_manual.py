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

import logging
import os
from dataclasses import dataclass
from importlib import reload
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
from opentelemetry.trace import NoOpTracerProvider, SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from opentelemetry.util._importlib_metadata import entry_points

from .mocks.api_gateway_http_api_event import (
    MOCK_LAMBDA_API_GATEWAY_HTTP_API_EVENT,
)
from .test_aws_lambda_instrumentation_base import (
    MOCK_LAMBDA_CONTEXT,
    MOCK_LAMBDA_CONTEXT_ATTRIBUTES,
    MOCK_W3C_BAGGAGE_KEY,
    MOCK_W3C_BAGGAGE_VALUE,
    MOCK_W3C_PARENT_SPAN_ID,
    MOCK_W3C_TRACE_CONTEXT_SAMPLED,
    MOCK_W3C_TRACE_ID,
    MOCK_W3C_TRACE_STATE_KEY,
    MOCK_W3C_TRACE_STATE_VALUE,
    MOCK_XRAY_PARENT_SPAN_ID,
    MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
    MOCK_XRAY_TRACE_CONTEXT_SAMPLED,
    MOCK_XRAY_TRACE_ID,
    TestAwsLambdaInstrumentorBase,
    mock_execute_lambda,
)


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
            assert span.kind == SpanKind.SERVER

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
