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
# type: ignore

import contextvars
import threading
import unittest
from unittest.mock import patch

from opentelemetry.instrumentation._labeler import (
    Labeler,
    clear_labeler,
    get_labeler,
    get_labeler_attributes,
    set_labeler,
)
from opentelemetry.instrumentation._labeler._internal import _labeler_context


class TestLabeler(unittest.TestCase):
    def setUp(self):
        clear_labeler()

    def test_labeler_init(self):
        labeler = Labeler()
        self.assertEqual(labeler.get_attributes(), {})
        self.assertEqual(len(labeler), 0)

    def test_add_single_attribute(self):
        labeler = Labeler()
        labeler.add("test_key", "test_value")
        attributes = labeler.get_attributes()
        self.assertEqual(attributes, {"test_key": "test_value"})
        self.assertEqual(len(labeler), 1)

    def test_add_multiple_attributes(self):
        labeler = Labeler()
        labeler.add("key1", "value1")
        labeler.add("key2", 42)
        labeler.add("key3", True)
        labeler.add("key4", 3.14)
        attributes = labeler.get_attributes()
        expected = {"key1": "value1", "key2": 42, "key3": True, "key4": 3.14}
        self.assertEqual(attributes, expected)
        self.assertEqual(len(labeler), 4)

    def test_add_attributes_dict(self):
        labeler = Labeler()
        attrs = {"key1": "value1", "key2": 42, "key3": False}
        labeler.add_attributes(attrs)
        attributes = labeler.get_attributes()
        self.assertEqual(attributes, attrs)

    def test_overwrite_attribute(self):
        labeler = Labeler()
        labeler.add("key1", "original")
        labeler.add("key1", "updated")
        attributes = labeler.get_attributes()
        self.assertEqual(attributes, {"key1": "updated"})

    def test_clear_attributes(self):
        labeler = Labeler()
        labeler.add("key1", "value1")
        labeler.add("key2", "value2")
        labeler.clear()
        self.assertEqual(labeler.get_attributes(), {})
        self.assertEqual(len(labeler), 0)

    def test_add_valid_types(self):
        labeler = Labeler()
        labeler.add("str_key", "string_value")
        labeler.add("int_key", 42)
        labeler.add("float_key", 3.14)
        labeler.add("bool_true_key", True)
        labeler.add("bool_false_key", False)

        attributes = labeler.get_attributes()
        expected = {
            "str_key": "string_value",
            "int_key": 42,
            "float_key": 3.14,
            "bool_true_key": True,
            "bool_false_key": False,
        }
        self.assertEqual(attributes, expected)
        self.assertEqual(len(labeler), 5)

    def test_add_invalid_types_logs_warning_and_skips(self):
        labeler = Labeler()

        with patch(
            "opentelemetry.instrumentation._labeler._internal._logger.warning"
        ) as mock_warning:
            labeler.add("valid", "value")

            labeler.add("dict_key", {"nested": "dict"})
            labeler.add("list_key", [1, 2, 3])
            labeler.add("none_key", None)
            labeler.add("tuple_key", (1, 2))
            labeler.add("set_key", {1, 2, 3})

            labeler.add("another_valid", 123)

        self.assertEqual(mock_warning.call_count, 5)
        warning_calls = [call[0] for call in mock_warning.call_args_list]
        self.assertIn("dict_key", str(warning_calls[0]))
        self.assertIn("dict", str(warning_calls[0]))
        self.assertIn("list_key", str(warning_calls[1]))
        self.assertIn("list", str(warning_calls[1]))
        self.assertIn("none_key", str(warning_calls[2]))
        self.assertIn("NoneType", str(warning_calls[2]))

        attributes = labeler.get_attributes()
        expected = {"valid": "value", "another_valid": 123}
        self.assertEqual(attributes, expected)
        self.assertEqual(len(labeler), 2)

    def test_add_attributes_valid_types(self):
        labeler = Labeler()
        attrs = {
            "str_key": "string_value",
            "int_key": 42,
            "float_key": 3.14,
            "bool_true_key": True,
            "bool_false_key": False,
        }
        labeler.add_attributes(attrs)
        attributes = labeler.get_attributes()
        self.assertEqual(attributes, attrs)
        self.assertEqual(len(labeler), 5)

    def test_add_attributes_invalid_types_logs_and_skips(self):
        labeler = Labeler()

        with patch(
            "opentelemetry.instrumentation._labeler._internal._logger.warning"
        ) as mock_warning:
            mixed_attrs = {
                "valid_str": "value",
                "invalid_dict": {"nested": "dict"},
                "valid_int": 42,
                "invalid_list": [1, 2, 3],
                "valid_bool": True,
                "invalid_none": None,
            }
            labeler.add_attributes(mixed_attrs)

        self.assertEqual(mock_warning.call_count, 3)
        warning_calls = [str(call) for call in mock_warning.call_args_list]
        self.assertTrue(any("invalid_dict" in call for call in warning_calls))
        self.assertTrue(any("invalid_list" in call for call in warning_calls))
        self.assertTrue(any("invalid_none" in call for call in warning_calls))
        attributes = labeler.get_attributes()
        expected = {
            "valid_str": "value",
            "valid_int": 42,
            "valid_bool": True,
        }
        self.assertEqual(attributes, expected)
        self.assertEqual(len(labeler), 3)

    def test_add_attributes_all_invalid_types(self):
        """Test add_attributes when all types are invalid"""
        labeler = Labeler()

        with patch(
            "opentelemetry.instrumentation._labeler._internal._logger.warning"
        ) as mock_warning:
            invalid_attrs = {
                "dict_key": {"nested": "dict"},
                "list_key": [1, 2, 3],
                "none_key": None,
                "custom_obj": object(),
            }

            labeler.add_attributes(invalid_attrs)

        # Should have logged warnings for all 4 invalid attributes
        self.assertEqual(mock_warning.call_count, 4)

        # No attributes should be stored
        attributes = labeler.get_attributes()
        self.assertEqual(attributes, {})
        self.assertEqual(len(labeler), 0)

    def test_thread_safety(self):
        labeler = Labeler(max_custom_attrs=1100)  # 11 * 100
        num_threads = 10
        num_operations = 100

        def worker(thread_id):
            for i_operation in range(num_operations):
                labeler.add(
                    f"thread_{thread_id}_key_{i_operation}",
                    f"value_{i_operation}",
                )
                # "shared" key that all 10 threads compete to write to
                labeler.add("shared", thread_id)

        # Start multiple threads
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=worker, args=(thread_id,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        attributes = labeler.get_attributes()
        # Should have all unique keys plus "shared"
        expected_unique_keys = num_threads * num_operations
        self.assertEqual(len(attributes), expected_unique_keys + 1)
        # "shared" key should exist and have some valid thread_id
        self.assertIn("shared", attributes)
        self.assertIn(attributes["shared"], range(num_threads))


class TestLabelerContext(unittest.TestCase):
    def setUp(self):
        clear_labeler()

    def test_get_labeler_creates_new(self):
        """Test that get_labeler creates a new labeler if none exists."""
        labeler = get_labeler()
        self.assertIsInstance(labeler, Labeler)
        self.assertEqual(labeler.get_attributes(), {})

    def test_get_labeler_returns_same_instance(self):
        """Test that get_labeler returns the same instance within context."""
        labeler1 = get_labeler()
        labeler1.add("test", "value")
        labeler2 = get_labeler()
        self.assertIs(labeler1, labeler2)
        self.assertEqual(labeler2.get_attributes(), {"test": "value"})

    def test_set_labeler(self):
        custom_labeler = Labeler()
        custom_labeler.add("custom", "value")
        set_labeler(custom_labeler)
        retrieved_labeler = get_labeler()
        self.assertIs(retrieved_labeler, custom_labeler)
        self.assertEqual(
            retrieved_labeler.get_attributes(), {"custom": "value"}
        )

    def test_clear_labeler(self):
        labeler = get_labeler()
        labeler.add("test", "value")
        clear_labeler()
        # Should get a new labeler after clearing
        new_labeler = get_labeler()
        self.assertIsNot(new_labeler, labeler)
        self.assertEqual(new_labeler.get_attributes(), {})

    def test_get_labeler_attributes(self):
        clear_labeler()
        attrs = get_labeler_attributes()
        self.assertEqual(attrs, {})
        labeler = get_labeler()
        labeler.add("test", "value")
        attrs = get_labeler_attributes()
        self.assertEqual(attrs, {"test": "value"})

    def test_context_isolation(self):
        def context_worker(context_id, results):
            labeler = get_labeler()
            labeler.add("context_id", context_id)
            labeler.add("value", f"context_{context_id}")
            results[context_id] = labeler.get_attributes()

        results = {}

        # Run in different contextvars contexts
        for i_operation in range(3):
            ctx = contextvars.copy_context()
            ctx.run(context_worker, i_operation, results)

        # Each context should have its own labeler with its own values
        for i_operation in range(3):
            expected = {
                "context_id": i_operation,
                "value": f"context_{i_operation}",
            }
            self.assertEqual(results[i_operation], expected)


class TestLabelerContextVar(unittest.TestCase):
    def setUp(self):
        clear_labeler()

    def test_contextvar_name_and_api_consistency(self):
        self.assertEqual(_labeler_context.name, "otel_labeler")
        labeler = get_labeler()
        labeler.add("test", "value")
        ctx_labeler = _labeler_context.get()
        self.assertIs(labeler, ctx_labeler)

    def test_contextvar_isolation(self):
        def context_worker(worker_id, results):
            labeler = get_labeler()
            labeler.add("worker_id", worker_id)
            results[worker_id] = labeler.get_attributes()

        results = {}
        for worker_id in range(3):
            ctx = contextvars.copy_context()
            ctx.run(context_worker, worker_id, results)
        for worker_id in range(3):
            expected = {"worker_id": worker_id}
            self.assertEqual(results[worker_id], expected)

    def test_clear_and_get_labeler_contextvar(self):
        labeler = get_labeler()
        labeler.add("test", "value")
        self.assertIs(_labeler_context.get(), labeler)
        clear_labeler()
        self.assertIsNone(_labeler_context.get())
        new_labeler = get_labeler()
        self.assertIsNot(new_labeler, labeler)
        self.assertEqual(new_labeler.get_attributes(), {})
