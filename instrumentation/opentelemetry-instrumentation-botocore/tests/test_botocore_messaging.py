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

from opentelemetry.instrumentation.botocore.extensions._messaging import (
    inject_propagation_context,
    message_attributes_setter,
)
from opentelemetry.test.test_base import TestBase


class TestMessageAttributes(TestBase):
    def test_message_attributes_setter(self):
        carrier = {}

        message_attributes_setter.set(carrier, "key", "value")
        self.assertEqual(
            {"key": {"DataType": "String", "StringValue": "value"}}, carrier
        )

    def test_inject_propagation_context(self):
        carrier = {
            "key1": {"DataType": "String", "StringValue": "value1"},
            "key2": {"DataType": "String", "StringValue": "value2"},
        }

        tracer = self.tracer_provider.get_tracer("test-tracer")
        with tracer.start_as_current_span("span"):
            inject_propagation_context(carrier)

        self.assertGreater(len(carrier), 2)

    def test_inject_propagation_context_too_many_attributes(self):
        carrier = {
            f"key{idx}": {"DataType": "String", "StringValue": f"value{idx}"}
            for idx in range(10)
        }
        tracer = self.tracer_provider.get_tracer("test-tracer")
        with tracer.start_as_current_span("span"):
            inject_propagation_context(carrier)

        self.assertEqual(10, len(carrier))
