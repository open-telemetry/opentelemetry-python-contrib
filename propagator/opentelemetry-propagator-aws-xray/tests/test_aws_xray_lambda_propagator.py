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

from os import environ
from unittest import TestCase
from unittest.mock import patch

from requests.structures import CaseInsensitiveDict

from opentelemetry.context import get_current
from opentelemetry.propagators.aws.aws_xray_propagator import (
    TRACE_HEADER_KEY,
    AwsXRayLambdaPropagator,
)
from opentelemetry.propagators.textmap import DefaultGetter
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import (
    Link,
    NonRecordingSpan,
    SpanContext,
    TraceState,
    get_current_span,
    use_span,
)
from opentelemetry.util._importlib_metadata import entry_points


class AwsXRayLambdaPropagatorTest(TestCase):
    def test_extract_no_environment_variable(self):
        actual_context = get_current_span(
            AwsXRayLambdaPropagator().extract(
                {}, context=get_current(), getter=DefaultGetter()
            )
        ).get_span_context()

        self.assertEqual(hex(actual_context.trace_id), "0x0")
        self.assertEqual(hex(actual_context.span_id), "0x0")
        self.assertFalse(
            actual_context.trace_flags.sampled,
        )
        self.assertEqual(actual_context.trace_state, TraceState.get_default())

    def test_extract_no_environment_variable_valid_context(self):
        with use_span(NonRecordingSpan(SpanContext(1, 2, False))):
            actual_context = get_current_span(
                AwsXRayLambdaPropagator().extract(
                    {}, context=get_current(), getter=DefaultGetter()
                )
            ).get_span_context()

            self.assertEqual(hex(actual_context.trace_id), "0x1")
            self.assertEqual(hex(actual_context.span_id), "0x2")
            self.assertFalse(
                actual_context.trace_flags.sampled,
            )
            self.assertEqual(
                actual_context.trace_state, TraceState.get_default()
            )

    @patch.dict(
        environ,
        {
            "_X_AMZN_TRACE_ID": (
                "Root=1-00000001-d188f8fa79d48a391a778fa6;"
                "Parent=53995c3f42cd8ad8;Sampled=1;Foo=Bar"
            )
        },
    )
    def test_extract_from_environment_variable(self):
        actual_context = get_current_span(
            AwsXRayLambdaPropagator().extract(
                {}, context=get_current(), getter=DefaultGetter()
            )
        ).get_span_context()

        self.assertEqual(
            hex(actual_context.trace_id), "0x1d188f8fa79d48a391a778fa6"
        )
        self.assertEqual(hex(actual_context.span_id), "0x53995c3f42cd8ad8")
        self.assertTrue(
            actual_context.trace_flags.sampled,
        )
        self.assertEqual(actual_context.trace_state, TraceState.get_default())

    @patch.dict(
        environ,
        {
            "_X_AMZN_TRACE_ID": (
                "Root=1-00000002-240000000000000000000002;"
                "Parent=1600000000000002;Sampled=1;Foo=Bar"
            )
        },
    )
    def test_add_link_from_environment_variable(self):
        propagator = AwsXRayLambdaPropagator()

        default_getter = DefaultGetter()

        carrier = CaseInsensitiveDict(
            {
                TRACE_HEADER_KEY: (
                    "Root=1-00000001-240000000000000000000001;"
                    "Parent=1600000000000001;Sampled=1"
                )
            }
        )

        extracted_context = propagator.extract(
            carrier, context=get_current(), getter=default_getter
        )

        link_context = propagator.extract(
            carrier, context=extracted_context, getter=default_getter
        )

        span = ReadableSpan(
            "test", parent=extracted_context, links=[Link(link_context)]
        )

        span_parent_context = get_current_span(span.parent).get_span_context()

        self.assertEqual(
            hex(span_parent_context.trace_id), "0x2240000000000000000000002"
        )
        self.assertEqual(
            hex(span_parent_context.span_id), "0x1600000000000002"
        )
        self.assertTrue(
            span_parent_context.trace_flags.sampled,
        )
        self.assertEqual(
            span_parent_context.trace_state, TraceState.get_default()
        )

        span_link_context = get_current_span(
            span.links[0].context
        ).get_span_context()

        self.assertEqual(
            hex(span_link_context.trace_id), "0x1240000000000000000000001"
        )
        self.assertEqual(hex(span_link_context.span_id), "0x1600000000000001")
        self.assertTrue(
            span_link_context.trace_flags.sampled,
        )
        self.assertEqual(
            span_link_context.trace_state, TraceState.get_default()
        )

    def test_load_entry_point(self):
        self.assertIs(
            next(
                iter(
                    entry_points(
                        group="opentelemetry_propagator", name="xray-lambda"
                    )
                )
            ).load(),
            AwsXRayLambdaPropagator,
        )
