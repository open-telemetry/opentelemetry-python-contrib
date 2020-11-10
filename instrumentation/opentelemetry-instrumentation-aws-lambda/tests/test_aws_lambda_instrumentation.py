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
import sys

from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor
from opentelemetry.test.test_base import TestBase


def lambda_handler(event, context):
    return event, context


def wrapper_handler(event, context):
    return lambda_handler(event, context)


class MockLambdaContext:
    pass


class TestAwsLambdaInstrumentor(TestBase):
    """AWS Lambda Instrumentation integration testsuite"""

    def setUp(self):
        super().setUp()
        os.environ[
            "_X_AMZN_TRACE_ID"
        ] = "Root=1-5f9f8bb1-3d0f7a5ef4dc8aa04da2bf6a;Parent=7e2d794cd396c754;Sampled=1"
        current_module = sys.modules[__name__]
        os.environ["_HANDLER"] = current_module.__name__ + ".lambda_handler"

        AwsLambdaInstrumentor().instrument()

        self._mock_context = MockLambdaContext()
        self._mock_context.invoked_function_arn = "arn://lambda-function-arn"
        self._mock_context.aws_request_id = "aws_request_id"

    def tearDown(self):
        AwsLambdaInstrumentor().uninstrument()
        super().tearDown()

    def test_instrumen_handler(self):
        lambda_handler("event", self._mock_context)
        spans = self.memory_exporter.get_finished_spans()

        assert spans
        span = spans[0]
        print(span)
        print(span.attributes)
        self.assertEqual(len(spans), 1)
        self.assertEqual(span.attributes["faas.execution"], "aws_request_id")

    def test_instrumen_wrapper_handler(self):
        current_module = sys.modules[__name__]
        os.environ["ORIG_HANDLER"] = (
            current_module.__name__ + ".lambda_handler"
        )
        os.environ["_HANDLER"] = current_module.__name__ + ".lambda_handler"

        AwsLambdaInstrumentor().instrument()

        wrapper_handler("event", self._mock_context)

        spans = self.memory_exporter.get_finished_spans()

        assert spans
        span = spans[0]

        self.assertEqual(len(spans), 1)
        self.assertEqual(span.attributes["faas.execution"], "aws_request_id")

    def test_uninstrument(self):
        AwsLambdaInstrumentor().uninstrument()

        lambda_handler("event", self._mock_context)

        spans = self.memory_exporter.get_finished_spans()
        assert not spans
        self.assertEqual(len(spans), 0)
