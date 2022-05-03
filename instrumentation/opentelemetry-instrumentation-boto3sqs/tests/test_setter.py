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

from opentelemetry.instrumentation.boto3sqs import (
    OPENTELEMETRY_ATTRIBUTE_IDENTIFIER,
    Boto3SQSSetter,
)


class TestBoto3SQSSetter(TestCase):
    def setUp(self) -> None:
        self.setter = Boto3SQSSetter()

    def test_simple(self):
        original_key = "SomeHeader"
        original_value = {"NumberValue": 1, "DataType": "Number"}
        carrier = {original_key: original_value.copy()}
        key = "test"
        value = "value"
        self.setter.set(carrier, key, value)
        # Ensure the original value is not harmed
        for dict_key, dict_val in carrier[original_key].items():
            self.assertEqual(original_value[dict_key], dict_val)
        # Ensure the new key is added well
        self.assertIn(
            f"{OPENTELEMETRY_ATTRIBUTE_IDENTIFIER}{key}", carrier.keys()
        )
        new_value = carrier[f"{OPENTELEMETRY_ATTRIBUTE_IDENTIFIER}{key}"]
        self.assertEqual(new_value["StringValue"], value)
