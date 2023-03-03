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

import asyncio
import io
import json
import sys
import zipfile

import aiobotocore.session
from moto import mock_iam, mock_lambda  # pylint: disable=import-error
from pytest import mark

from opentelemetry.instrumentation.aiobotocore import AioBotocoreInstrumentor
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace.span import Span


def async_call(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def get_as_zip_file(file_name, content):
    zip_output = io.BytesIO()
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(file_name, content)
    zip_output.seek(0)
    return zip_output.read()


def return_headers_lambda_str():
    pfunc = """
def lambda_handler(event, context):
    print("custom log event")
    headers = event.get('headers', event.get('attributes', {}))
    return headers
"""
    return pfunc


class TestLambdaExtension(TestBase):
    def setUp(self):
        super().setUp()
        AioBotocoreInstrumentor().instrument()

        session = aiobotocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"
        self.client = async_call(
            session.create_client(
                "lambda", region_name=self.region
            ).__aenter__()
        )
        self.iam_client = async_call(
            session.create_client("iam", region_name=self.region).__aenter__()
        )

    def tearDown(self):
        super().tearDown()
        AioBotocoreInstrumentor().uninstrument()

    def assert_span(self, operation: str) -> Span:
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))

        span = spans[0]
        self.assertEqual(operation, span.attributes[SpanAttributes.RPC_METHOD])
        self.assertEqual("Lambda", span.attributes[SpanAttributes.RPC_SERVICE])
        self.assertEqual("aws-api", span.attributes[SpanAttributes.RPC_SYSTEM])
        return span

    def assert_invoke_span(self, function_name: str) -> Span:
        span = self.assert_span("Invoke")
        self.assertEqual(
            "aws", span.attributes[SpanAttributes.FAAS_INVOKED_PROVIDER]
        )
        self.assertEqual(
            self.region, span.attributes[SpanAttributes.FAAS_INVOKED_REGION]
        )
        self.assertEqual(
            function_name, span.attributes[SpanAttributes.FAAS_INVOKED_NAME]
        )
        return span

    @mock_lambda
    def test_list_functions(self):
        async_call(self.client.list_functions())
        self.assert_span("ListFunctions")

    @mock_iam
    def _create_role_and_get_arn(self) -> str:
        return async_call(
            self.iam_client.create_role(
                RoleName="my-role",
                AssumeRolePolicyDocument="some policy",
                Path="/my-path/",
            )
        )["Role"]["Arn"]

    def _create_lambda_function(self, function_name: str, function_code: str):
        role_arn = self._create_role_and_get_arn()

        async_call(
            self.client.create_function(
                FunctionName=function_name,
                Runtime="python3.8",
                Role=role_arn,
                Handler="lambda_function.lambda_handler",
                Code={
                    "ZipFile": get_as_zip_file(
                        "lambda_function.py", function_code
                    )
                },
                Description="test lambda function",
                Timeout=3,
                MemorySize=128,
                Publish=True,
            )
        )

    @mark.skip(reason="Docker error, unblocking builds for now.")
    @mark.skipif(
        sys.platform == "win32",
        reason="requires docker and Github CI Windows does not have docker installed by default",
    )
    @mock_lambda
    def test_invoke(self):
        previous_propagator = get_global_textmap()
        try:
            set_global_textmap(MockTextMapPropagator())
            function_name = "testFunction"
            self._create_lambda_function(
                function_name, return_headers_lambda_str()
            )
            # 2 spans for create IAM + create lambda
            self.assertEqual(2, len(self.memory_exporter.get_finished_spans()))
            self.memory_exporter.clear()

            response = async_call(
                self.client.invoke(
                    Payload=json.dumps({}),
                    FunctionName=function_name,
                    InvocationType="RequestResponse",
                )
            )

            span = self.assert_invoke_span(function_name)
            span_context = span.get_span_context()

            # # assert injected span
            headers = json.loads(response["Payload"].read().decode("utf-8"))
            self.assertEqual(
                str(span_context.trace_id),
                headers[MockTextMapPropagator.TRACE_ID_KEY],
            )
            self.assertEqual(
                str(span_context.span_id),
                headers[MockTextMapPropagator.SPAN_ID_KEY],
            )
        finally:
            set_global_textmap(previous_propagator)
