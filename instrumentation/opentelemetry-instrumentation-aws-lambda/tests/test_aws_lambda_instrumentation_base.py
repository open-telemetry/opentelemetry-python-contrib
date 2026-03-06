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
from importlib import import_module
from unittest import mock

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.aws_lambda import (
    _HANDLER,
    AwsLambdaInstrumentor,
)
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
)
from opentelemetry.test.test_base import TestBase


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
MOCK_XRAY_TRACE_CONTEXT_COMMON = (
    f"Root={TRACE_ID_VERSION}"
    f"-{MOCK_XRAY_TRACE_ID_STR[:TRACE_ID_FIRST_PART_LENGTH]}"
    f"-{MOCK_XRAY_TRACE_ID_STR[TRACE_ID_FIRST_PART_LENGTH:]}"
    f";Parent={MOCK_XRAY_PARENT_SPAN_ID:x}"
)
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
        _OpenTelemetrySemanticConventionStability._initialized = False

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
