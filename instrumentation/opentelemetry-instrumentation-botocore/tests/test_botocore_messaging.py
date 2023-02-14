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
import json
from typing import Any, MutableMapping

from opentelemetry.instrumentation.botocore.extensions._messaging import (
    extract_propagation_context,
    inject_propagation_context,
    message_attributes_getter,
    message_attributes_setter,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace.span import (
    INVALID_SPAN,
    format_span_id,
    format_trace_id,
)


def _add_trace_parent(
    message: MutableMapping[str, Any], trace_id: int, span_id: int
):
    attrs = message.setdefault("MessageAttributes", {})
    attrs["traceparent"] = {
        "DataType": "String",
        "StringValue": f"00-{format_trace_id(trace_id)}-{format_span_id(span_id)}-01",
    }
    return message


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

    def test_message_attributes_getter(self):
        carrier = {
            "sqs-key": {"DataType": "String", "StringValue": "sqs-value"},
            "sns-key": {"Type": "String", "Value": "sns-value"},
            "other": {"some": "value"},
            "other2": "value",
        }

        self.assertEqual(
            ["sqs-value"], message_attributes_getter.get(carrier, "sqs-key")
        )
        self.assertEqual(
            ["sns-value"], message_attributes_getter.get(carrier, "sns-key")
        )
        self.assertIsNone(message_attributes_getter.get(carrier, "other"))
        self.assertIsNone(message_attributes_getter.get(carrier, "other2"))

    def test_extract_propagation_context(self):
        message = _add_trace_parent({}, 17, 42)
        span = extract_propagation_context(message)
        self.assertEqual(17, span.get_span_context().trace_id)
        self.assertEqual(42, span.get_span_context().span_id)

    def test_extract_propagation_context_from_payload(self):
        message = {"Body": json.dumps(_add_trace_parent({}, 17, 42))}
        span = extract_propagation_context(message, extract_from_payload=False)
        self.assertIs(INVALID_SPAN, span)

        span = extract_propagation_context(message, extract_from_payload=True)
        self.assertEqual(17, span.get_span_context().trace_id)
        self.assertEqual(42, span.get_span_context().span_id)

    def test_extract_propagation_context_from_payload_without_msg_attrs(self):
        message = {"Body": "{}"}
        self.assertIs(
            INVALID_SPAN,
            extract_propagation_context(message, extract_from_payload=True),
        )

    def test_extract_propagation_context_from_malformed_payload(self):
        message = {"Body": '{"MessageAttributes": {'}
        self.assertIs(
            INVALID_SPAN,
            extract_propagation_context(message, extract_from_payload=True),
        )

    def test_extract_propagation_context_from_non_dict_payload(self):
        message = {"Body": "123"}
        self.assertIs(
            INVALID_SPAN,
            extract_propagation_context(message, extract_from_payload=True),
        )
