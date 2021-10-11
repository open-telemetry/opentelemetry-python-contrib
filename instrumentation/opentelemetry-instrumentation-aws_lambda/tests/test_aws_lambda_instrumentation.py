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
import fileinput
import os
import sys
from importlib import import_module, reload
from shutil import which
from unittest import mock

from opentelemetry.environment_variables import OTEL_PROPAGATORS
from opentelemetry.instrumentation.aws_lambda import (
    _HANDLER,
    _X_AMZN_TRACE_ID,
    ORIG_HANDLER,
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
from opentelemetry.trace import SpanKind
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

AWS_LAMBDA_EXEC_WRAPPER = "AWS_LAMBDA_EXEC_WRAPPER"
CONFIGURE_OTEL_SDK_SCRIPTS_DIR = os.path.join(
    *(os.path.dirname(__file__), "..", "scripts")
)
TOX_PYTHON_DIRECTORY = os.path.dirname(os.path.dirname(which("python3")))


class MockLambdaContext:
    def __init__(self, aws_request_id, invoked_function_arn):
        self.invoked_function_arn = invoked_function_arn
        self.aws_request_id = aws_request_id


MOCK_LAMBDA_CONTEXT = MockLambdaContext(
    aws_request_id="mock_aws_request_id",
    invoked_function_arn="arn://mock-lambda-function-arn",
)

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


def replace_in_file(file_path, search_text, new_text):
    with fileinput.input(file_path, inplace=True) as file_object:
        for line in file_object:
            new_line = line.replace(search_text, new_text)
            # This directs the output to the file, not the console
            print(new_line, end="")


def mock_aws_lambda_exec_wrapper():
    """Mocks automatically instrumenting user Lambda function by pointing
    `AWS_LAMBDA_EXEC_WRAPPER` to the
    `otel-instrument` script.

    See more:
    https://aws-otel.github.io/docs/getting-started/lambda/lambda-python
    """

    # NOTE: Do NOT run as a sub process because this script needs to update
    # the environment variables in this same process.

    original_sys_argv = sys.argv
    otel_instrument_file = os.path.join(
        CONFIGURE_OTEL_SDK_SCRIPTS_DIR, "otel-instrument"
    )
    sys.argv = [
        otel_instrument_file,
        which("python3"),
        "-c",
        "pass",
    ]
    with open(otel_instrument_file) as config_otel_script:
        exec(config_otel_script.read())
    sys.argv = original_sys_argv


def mock_execute_lambda(event=None, should_reload=True):
    """Mocks the AWS Lambda execution. Like the real Lambda, if
    `AWS_LAMBDA_EXEC_WRAPPER` is defined, it calls that script first.

    NOTE: Normally AWS Lambda would give the script the arguments used to start
    the program. We don't do that because we want to give the code below which
    mocks the `/var/runtime/bootstrap.py` starter file different Lambda event
    test cases. We don't want `bootstrap.py` to constrcut them.

    NOTE: We can't use `moto`'s `mock_lambda` because it does not support
    AWS_LAMBDA_EXEC_WRAPPER and doesn't mimic the reload behavior we have here.

    See more:
    https://docs.aws.amazon.com/lambda/latest/dg/runtimes-modify.html#runtime-wrapper

    Args:
        event: The Lambda event which may or may not be used by instrumentation.
        should_reload: Whether to reload the import of the module. This is
            import for auto-instrumentation tests because they are importing the
            same `otel_wrapper.py` file. We skip this for manual-instrumentation
            test because otherwise the reload would get rid of the patching done
            by `AwsLambdaInstrumentor.()instrument()` in the test case.
    """
    if os.environ[AWS_LAMBDA_EXEC_WRAPPER]:
        globals()[os.environ[AWS_LAMBDA_EXEC_WRAPPER]]()

    # NOTE: Mocks Lambda's `python3 /var/runtime/bootstrap.py`. Which _reloads_
    # the import of a module using the deprecated `imp.load_module`. This is
    # prevents us from simply using `otel-instrument`, and what requires that we
    # use `otel_wrapper.py` as well.
    #
    # See more:
    # https://docs.python.org/3/library/imp.html#imp.load_module

    module_name, handler_name = os.environ[_HANDLER].rsplit(".", 1)
    handler_module = import_module(module_name.replace("/", "."))

    if should_reload:

        # NOTE: The first time, this reload produces a `warning` that we are
        # "Attempting to instrument while already instrumented". This is fine
        # because we are simulating Lambda's "reloading" import so we
        # instrument twice.
        #
        # TODO: (NathanielRN) On subsequent tests, the first import above does
        # not run `instrument()` on import. Only `reload` below will run it, no
        # warning appears in the logs. Instrumentation still works fine if we
        # remove the reload. Not sure why this happens.

        handler_module = reload(handler_module)

    getattr(handler_module, handler_name)(event, MOCK_LAMBDA_CONTEXT)


class TestAwsLambdaInstrumentor(TestBase):
    """AWS Lambda Instrumentation Testsuite"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.path.append(CONFIGURE_OTEL_SDK_SCRIPTS_DIR)
        replace_in_file(
            os.path.join(CONFIGURE_OTEL_SDK_SCRIPTS_DIR, "otel-instrument"),
            'LAMBDA_LAYER_PKGS_DIR = os.path.abspath(os.path.join(os.sep, "opt", "python"))',
            f'LAMBDA_LAYER_PKGS_DIR = "{TOX_PYTHON_DIRECTORY}"',
        )

    def setUp(self):
        super().setUp()
        self.common_env_patch = mock.patch.dict(
            "os.environ",
            {
                AWS_LAMBDA_EXEC_WRAPPER: "mock_aws_lambda_exec_wrapper",
                "AWS_LAMBDA_FUNCTION_NAME": "test-python-lambda-function",
                "AWS_LAMBDA_FUNCTION_VERSION": "2",
                "AWS_REGION": "us-east-1",
                _HANDLER: "mocks.lambda_function.handler",
                "LAMBDA_RUNTIME_DIR": "mock-directory-since-tox-knows-pkgs-loc",
            },
        )
        self.common_env_patch.start()

        # NOTE: Whether AwsLambdaInstrumentor().instrument() is run id decided
        # by each test case. It depends on if the test is for auto or manual
        # instrumentation.

    def tearDown(self):
        super().tearDown()
        self.common_env_patch.stop()
        AwsLambdaInstrumentor().uninstrument()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        sys.path.remove(CONFIGURE_OTEL_SDK_SCRIPTS_DIR)
        replace_in_file(
            os.path.join(CONFIGURE_OTEL_SDK_SCRIPTS_DIR, "otel-instrument"),
            f'LAMBDA_LAYER_PKGS_DIR = "{TOX_PYTHON_DIRECTORY}"',
            'LAMBDA_LAYER_PKGS_DIR = os.path.abspath(os.path.join(os.sep, "opt", "python"))',
        )

    # MARK: Auto Instrumentation Tests

    def test_active_tracing(self):
        test_env_patch = mock.patch.dict(
            "os.environ",
            {
                **os.environ,
                # Using Active tracing
                _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_SAMPLED,
            },
        )
        test_env_patch.start()

        mock_execute_lambda()

        spans = self.memory_exporter.get_finished_spans()

        assert spans

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, os.environ[ORIG_HANDLER])
        self.assertEqual(span.get_span_context().trace_id, MOCK_XRAY_TRACE_ID)
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            span,
            {
                ResourceAttributes.FAAS_ID: MOCK_LAMBDA_CONTEXT.invoked_function_arn,
                SpanAttributes.FAAS_EXECUTION: MOCK_LAMBDA_CONTEXT.aws_request_id,
            },
        )

        # TODO: Waiting on OTel Python support for setting Resource Detectors
        # using environment variables. Auto Instrumentation (used by this Lambda
        # Instrumentation) sets up the global TracerProvider which is the only
        # time Resource Detectors can be configured.
        #
        # environ["OTEL_RESOURCE_DETECTORS"] = "aws_lambda"
        #
        # We would configure this environment variable in
        # `otel-instrument`.
        #
        # res_atts = span.resource.attributes
        # self.assertEqual(res_atts[ResourceAttributes.CLOUD_PLATFORM], CloudPlatformValues.AWS_LAMBDA.value)
        # self.assertEqual(res_atts[ResourceAttributes.CLOUD_PROVIDER], CloudProviderValues.AWS.value)
        # self.assertEqual(res_atts[ResourceAttributes.CLOUD_REGION], os.environ["AWS_REGION"])
        # self.assertEqual(res_atts[ResourceAttributes.FAAS_NAME], os.environ["AWS_LAMBDA_FUNCTION_NAME"])
        # self.assertEqual(res_atts[ResourceAttributes.FAAS_VERSION], os.environ["AWS_LAMBDA_FUNCTION_VERSION"])

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_XRAY_PARENT_SPAN_ID)
        self.assertTrue(parent_context.is_remote)

        test_env_patch.stop()

    def test_parent_context_from_lambda_event(self):
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

        mock_execute_lambda(
            {
                "headers": {
                    TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                    TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                }
            }
        )

        spans = self.memory_exporter.get_finished_spans()

        assert spans

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.get_span_context().trace_id, MOCK_W3C_TRACE_ID)

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_W3C_PARENT_SPAN_ID)
        self.assertEqual(len(parent_context.trace_state), 3)
        self.assertEqual(
            parent_context.trace_state.get(MOCK_W3C_TRACE_STATE_KEY),
            MOCK_W3C_TRACE_STATE_VALUE,
        )
        self.assertTrue(parent_context.is_remote)

        test_env_patch.stop()

    # MARK: Manual Instrumentation Tests

    def test_using_custom_extractor(self):
        def custom_event_context_extractor(lambda_event):
            return get_global_textmap().extract(lambda_event["foo"]["headers"])

        test_env_patch = mock.patch.dict(
            "os.environ",
            {
                **os.environ,
                # DO NOT use `otel-instrument` script, resort to "manual"
                # instrumentation as seen below
                AWS_LAMBDA_EXEC_WRAPPER: "",
                # NOT Active Tracing
                _X_AMZN_TRACE_ID: MOCK_XRAY_TRACE_CONTEXT_NOT_SAMPLED,
                # NOT using the X-Ray Propagator
                OTEL_PROPAGATORS: "tracecontext",
            },
        )
        test_env_patch.start()

        AwsLambdaInstrumentor().instrument(
            event_context_extractor=custom_event_context_extractor,
        )

        mock_execute_lambda(
            {
                "foo": {
                    "headers": {
                        TraceContextTextMapPropagator._TRACEPARENT_HEADER_NAME: MOCK_W3C_TRACE_CONTEXT_SAMPLED,
                        TraceContextTextMapPropagator._TRACESTATE_HEADER_NAME: f"{MOCK_W3C_TRACE_STATE_KEY}={MOCK_W3C_TRACE_STATE_VALUE},foo=1,bar=2",
                    }
                }
            },
            should_reload=False,
        )

        spans = self.memory_exporter.get_finished_spans()

        assert spans

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.get_span_context().trace_id, MOCK_W3C_TRACE_ID)

        parent_context = span.parent
        self.assertEqual(
            parent_context.trace_id, span.get_span_context().trace_id
        )
        self.assertEqual(parent_context.span_id, MOCK_W3C_PARENT_SPAN_ID)
        self.assertEqual(len(parent_context.trace_state), 3)
        self.assertEqual(
            parent_context.trace_state.get(MOCK_W3C_TRACE_STATE_KEY),
            MOCK_W3C_TRACE_STATE_VALUE,
        )
        self.assertTrue(parent_context.is_remote)

        test_env_patch.stop()
