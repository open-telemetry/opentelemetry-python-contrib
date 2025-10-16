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

import unittest
from unittest import mock

from taskiq import TaskiqMessage

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.taskiq import utils
from opentelemetry.sdk import trace

from .taskiq_test_tasks import broker


class TestUtils(unittest.TestCase):
    def setUp(self):
        self.broker = broker

    def test_set_attributes_from_context(self):
        # it should extract only relevant keys
        context = {
            "_retries": "4",
            "delay": "30",
            "max_retries": "6",
            "retry_on_error": "true",
            "timeout": "60",
            "X-Taskiq-requeue": "4",
            "custom_meta": "custom_value",
        }

        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))
        utils.set_attributes_from_context(span, context)

        self.assertEqual(span.attributes.get("taskiq._retries"), "4")
        self.assertEqual(span.attributes.get("taskiq.delay"), "30")
        self.assertEqual(span.attributes.get("taskiq.max_retries"), "6")
        self.assertEqual(span.attributes.get("taskiq.retry_on_error"), "true")
        self.assertEqual(span.attributes.get("taskiq.timeout"), "60")
        self.assertEqual(span.attributes.get("taskiq.X-Taskiq-requeue"), "4")

        self.assertNotIn("custom_meta", span.attributes)

    def test_set_attributes_not_recording(self):
        # it should extract only relevant keys
        context = {
            "_retries": "4",
            "delay": "30",
            "max_retries": "6",
            "retry_on_error": "true",
            "timeout": "60",
            "X-Taskiq-requeue": "4",
            "custom_meta": "custom_value",
        }

        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        utils.set_attributes_from_context(mock_span, context)
        self.assertFalse(mock_span.is_recording())
        self.assertTrue(mock_span.is_recording.called)
        self.assertFalse(mock_span.set_attribute.called)
        self.assertFalse(mock_span.set_status.called)

    def test_set_attributes_from_context_empty_keys(self):
        # it should not extract empty keys
        context = {
            "retries": 0,
        }

        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))
        utils.set_attributes_from_context(span, context)

        self.assertEqual(len(span.attributes), 0)

    def test_span_propagation(self):
        # propagate and retrieve a Span
        message = mock.Mock(
            task_id="7c6731af-9533-40c3-83a9-25b58f0d837f", spec=TaskiqMessage
        )
        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))
        utils.attach_context(message, span, mock.Mock(), "")
        ctx = utils.retrieve_context(message)
        self.assertIsNotNone(ctx)
        span_after, _, _ = ctx
        self.assertIs(span, span_after)

    def test_span_delete(self):
        # propagate a Span
        message = mock.Mock(
            task_id="7c6731af-9533-40c3-83a9-25b58f0d837f", spec=TaskiqMessage
        )
        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))
        utils.attach_context(message, span, mock.Mock(), "")
        # delete the Span
        utils.detach_context(message)
        self.assertEqual(utils.retrieve_context(message), None)

    def test_optional_message_span_attach(self):
        span = trace._Span("name", mock.Mock(spec=trace_api.SpanContext))

        # assert this is is a no-aop
        self.assertIsNone(utils.attach_context(None, span, mock.Mock(), ""))

    def test_span_delete_empty(self):
        # delete the Span
        message = mock.Mock(
            task_id="7c6731af-9533-40c3-83a9-25b58f0d837f", spec=TaskiqMessage
        )
        try:
            utils.detach_context(message)
            self.assertEqual(utils.retrieve_context(message), None)
        except Exception as ex:  # pylint: disable=broad-except
            self.fail(f"Exception was raised: {ex}")
