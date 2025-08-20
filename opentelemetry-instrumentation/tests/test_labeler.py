"""
Test cases for the common Labeler functionality in opentelemetry-instrumentation.
"""

import contextvars
import threading
import unittest

from opentelemetry.instrumentation._labeler import (
    Labeler,
    clear_labeler,
    get_labeler,
    get_labeler_attributes,
    set_labeler,
)


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

    def test_invalid_attribute_types(self):
        labeler = Labeler()

        with self.assertRaises(ValueError):
            labeler.add("key", [1, 2, 3])

        with self.assertRaises(ValueError):
            labeler.add("key", {"nested": "dict"})

        with self.assertRaises(ValueError):
            labeler.add_attributes({"key": None})

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

    def test_thread_safety(self):
        labeler = Labeler()
        num_threads = 10
        num_operations = 100

        def worker(thread_id):
            for i in range(num_operations):
                labeler.add(f"thread_{thread_id}_key_{i}", f"value_{i}")

        # Start multiple threads
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=worker, args=(thread_id,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check that all attributes were added
        attributes = labeler.get_attributes()
        expected_count = num_threads * num_operations
        self.assertEqual(len(attributes), expected_count)


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
        for i in range(3):
            ctx = contextvars.copy_context()
            ctx.run(context_worker, i, results)

        # Each context should have its own labeler with its own values
        for i in range(3):
            expected = {"context_id": i, "value": f"context_{i}"}
            self.assertEqual(results[i], expected)
