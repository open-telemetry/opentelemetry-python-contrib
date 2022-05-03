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

# pylint: disable=no-name-in-module

from unittest import TestCase

import boto3
import botocore.client
from wrapt import BoundFunctionWrapper, FunctionWrapper

from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor


# pylint: disable=attribute-defined-outside-init
class TestBoto3SQSInstrumentor(TestCase):
    def define_sqs_mock(self) -> None:
        # pylint: disable=R0201
        class SQSClientMock(botocore.client.BaseClient):
            def send_message(self, *args, **kwargs):
                ...

            def send_message_batch(self, *args, **kwargs):
                ...

            def receive_message(self, *args, **kwargs):
                ...

            def delete_message(self, *args, **kwargs):
                ...

            def delete_message_batch(self, *args, **kwargs):
                ...

        self._boto_sqs_mock = SQSClientMock

    def test_instrument_api_before_client_init(self) -> None:
        instrumentation = Boto3SQSInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(boto3.client, FunctionWrapper))
        instrumentation.uninstrument()

    def test_instrument_api_after_client_init(self) -> None:
        self.define_sqs_mock()
        instrumentation = Boto3SQSInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(boto3.client, FunctionWrapper))
        self.assertTrue(
            isinstance(self._boto_sqs_mock.send_message, BoundFunctionWrapper)
        )
        self.assertTrue(
            isinstance(
                self._boto_sqs_mock.send_message_batch, BoundFunctionWrapper
            )
        )
        self.assertTrue(
            isinstance(
                self._boto_sqs_mock.receive_message, BoundFunctionWrapper
            )
        )
        self.assertTrue(
            isinstance(
                self._boto_sqs_mock.delete_message, BoundFunctionWrapper
            )
        )
        self.assertTrue(
            isinstance(
                self._boto_sqs_mock.delete_message_batch, BoundFunctionWrapper
            )
        )
        instrumentation.uninstrument()
