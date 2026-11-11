# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from asyncio import CancelledError
from unittest import TestCase
from unittest.mock import Mock, call

from opentelemetry.instrumentation._semconv import _record_error_type, _set_error_type
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE


class TestSetErrorType(TestCase):
    def test_sets_canonical_class_name_on_span_and_metric_attributes(self):
        span = Mock()
        span.is_recording.return_value = True
        metric_attributes = {}

        returned = _set_error_type(ValueError("boom"), span, metric_attributes)

        self.assertEqual(returned, "ValueError")
        span.set_attribute.assert_called_once_with(ERROR_TYPE, "ValueError")
        self.assertEqual(metric_attributes, {ERROR_TYPE: "ValueError"})

    def test_uses_qualname_for_a_nested_exception_class(self):
        class Outer:
            class Failure(Exception):
                pass

        metric_attributes = {}

        _set_error_type(Outer.Failure(), None, metric_attributes)

        self.assertEqual(
            metric_attributes,
            {ERROR_TYPE: "TestSetErrorType.test_uses_qualname_for_a_nested_exception_class.<locals>.Outer.Failure"},
        )

    def test_does_not_touch_a_span_that_is_not_recording(self):
        span = Mock()
        span.is_recording.return_value = False

        _set_error_type(ValueError("boom"), span)

        self.assertEqual(span.set_attribute.call_args_list, [])

    def test_accepts_a_span_without_metric_attributes(self):
        span = Mock()
        span.is_recording.return_value = True

        _set_error_type(KeyError("boom"), span)

        self.assertEqual(span.set_attribute.call_args_list, [call(ERROR_TYPE, "KeyError")])

    def test_accepts_metric_attributes_without_a_span(self):
        metric_attributes = {}

        _set_error_type(KeyError("boom"), None, metric_attributes)

        self.assertEqual(metric_attributes, {ERROR_TYPE: "KeyError"})


class TestRecordErrorType(TestCase):
    def test_records_nothing_when_the_block_succeeds(self):
        span = Mock()
        span.is_recording.return_value = True
        metric_attributes = {}

        with _record_error_type(span, metric_attributes):
            pass

        span.set_attribute.assert_not_called()
        self.assertEqual(metric_attributes, {})

    def test_records_both_destinations_when_the_block_raises(self):
        span = Mock()
        span.is_recording.return_value = True
        metric_attributes = {}

        with self.assertRaises(ValueError):
            with _record_error_type(span, metric_attributes):
                raise ValueError("boom")

        span.set_attribute.assert_called_once_with(ERROR_TYPE, "ValueError")
        self.assertEqual(metric_attributes, {ERROR_TYPE: "ValueError"})

    def test_reraises_the_original_exception_object_unmodified(self):
        span = Mock()
        span.is_recording.return_value = True
        raised = ValueError("boom")

        with self.assertRaises(ValueError) as caught:
            with _record_error_type(span):
                raise raised

        self.assertIs(caught.exception, raised)
        self.assertEqual(str(caught.exception), "boom")

    def test_lets_a_base_exception_through_without_recording(self):
        span = Mock()
        span.is_recording.return_value = True
        metric_attributes = {}

        with self.assertRaises(KeyboardInterrupt):
            with _record_error_type(span, metric_attributes):
                raise KeyboardInterrupt

        span.set_attribute.assert_not_called()
        self.assertEqual(metric_attributes, {})

    def test_lets_a_cancellation_through_without_recording(self):
        span = Mock()
        span.is_recording.return_value = True

        with self.assertRaises(CancelledError):
            with _record_error_type(span):
                raise CancelledError

        span.set_attribute.assert_not_called()
