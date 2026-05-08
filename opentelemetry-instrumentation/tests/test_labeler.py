# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextvars
import threading
import unittest
from unittest.mock import patch

from opentelemetry.instrumentation._labeler import (
    Labeler,
    clear_labeler,
    enrich_metric_attributes,
    get_labeler,
    get_labeler_attributes,
    set_labeler,
)
from opentelemetry.instrumentation._labeler._internal import (
    LABELER_CONTEXT_KEY,
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
        self.assertEqual(labeler.get_attributes(), {"test_key": "test_value"})

    def test_add_attributes_dict(self):
        labeler = Labeler()
        attrs = {"key1": "value1", "key2": 42, "key3": False}
        labeler.add_attributes(attrs)
        self.assertEqual(labeler.get_attributes(), attrs)

    def test_overwrite_attribute(self):
        labeler = Labeler()
        labeler.add("key1", "original")
        labeler.add("key1", "updated")
        self.assertEqual(labeler.get_attributes(), {"key1": "updated"})

    def test_clear_attributes(self):
        labeler = Labeler()
        labeler.add("key1", "value1")
        labeler.add("key2", "value2")
        labeler.clear()
        self.assertEqual(labeler.get_attributes(), {})

    def test_add_invalid_types_logs_warning_and_skips(self):
        labeler = Labeler()
        with patch(
            "opentelemetry.instrumentation._labeler._internal._logger.warning"
        ) as mock_warning:
            labeler.add("valid", "value")
            labeler.add("dict_key", {"nested": "dict"})
            labeler.add("list_key", [1, 2, 3])
            labeler.add("none_key", None)
            labeler.add("another_valid", 123)

        self.assertEqual(mock_warning.call_count, 3)
        self.assertEqual(
            labeler.get_attributes(), {"valid": "value", "another_valid": 123}
        )

    def test_limit_and_truncation(self):
        labeler = Labeler(max_custom_attrs=2, max_attr_value_length=5)
        labeler.add("a", "1234567")
        labeler.add("b", "ok")
        labeler.add("c", "ignored")
        self.assertEqual(labeler.get_attributes(), {"a": "12345", "b": "ok"})

    def test_enrich_metric_attributes_skips_base_overrides(self):
        base_attributes = {"http.method": "GET", "http.status_code": 200}
        labeler = get_labeler()
        labeler.add("http.method", "POST")
        labeler.add("custom_attr", "test-value")

        enriched = enrich_metric_attributes(base_attributes)
        self.assertEqual(enriched["http.method"], "GET")
        self.assertEqual(enriched["custom_attr"], "test-value")
        self.assertEqual(base_attributes["http.method"], "GET")

    def test_thread_safety(self):
        labeler = Labeler(max_custom_attrs=1100)
        num_threads = 5
        num_ops = 100

        def worker(thread_id):
            for index in range(num_ops):
                labeler.add(f"thread_{thread_id}_{index}", f"v_{index}")

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(num_threads)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(labeler.get_attributes()), num_threads * num_ops)


class TestLabelerContext(unittest.TestCase):
    def setUp(self):
        clear_labeler()

    def test_get_labeler_creates_new(self):
        labeler = get_labeler()
        self.assertIsInstance(labeler, Labeler)

    def test_get_labeler_returns_same_instance(self):
        labeler1 = get_labeler()
        labeler1.add("test", "value")
        labeler2 = get_labeler()
        self.assertIs(labeler1, labeler2)

    def test_set_labeler(self):
        custom_labeler = Labeler()
        custom_labeler.add("custom", "value")
        set_labeler(custom_labeler)
        self.assertIs(get_labeler(), custom_labeler)

    def test_set_labeler_invalid_type_is_ignored(self):
        with patch(
            "opentelemetry.instrumentation._labeler._internal._logger.warning"
        ) as mock_warning:
            set_labeler("bad")  # type: ignore[arg-type]
        self.assertEqual(mock_warning.call_count, 1)

    def test_clear_labeler(self):
        labeler = get_labeler()
        labeler.add("test", "value")
        clear_labeler()
        new_labeler = get_labeler()
        self.assertIsNot(new_labeler, labeler)
        self.assertEqual(new_labeler.get_attributes(), {})

    def test_get_labeler_attributes(self):
        clear_labeler()
        self.assertEqual(get_labeler_attributes(), {})
        labeler = get_labeler()
        labeler.add("test", "value")
        self.assertEqual(get_labeler_attributes(), {"test": "value"})

    def test_context_isolation(self):
        def context_worker(context_id, results):
            labeler = get_labeler()
            labeler.add("context_id", context_id)
            results[context_id] = dict(labeler.get_attributes())

        results = {}
        for operation in range(3):
            ctx = contextvars.copy_context()
            ctx.run(context_worker, operation, results)

        for operation in range(3):
            self.assertEqual(results[operation], {"context_id": operation})


class TestLabelerFailSafe(unittest.TestCase):
    def setUp(self):
        clear_labeler()

    def test_get_labeler_failsafe_on_get_value_error(self):
        with patch(
            "opentelemetry.instrumentation._labeler._internal.get_value",
            side_effect=RuntimeError("boom"),
        ):
            labeler = get_labeler()
        self.assertIsInstance(labeler, Labeler)

    def test_set_and_clear_failsafe_on_attach_error(self):
        labeler = Labeler()
        with patch(
            "opentelemetry.instrumentation._labeler._internal.attach",
            side_effect=RuntimeError("boom"),
        ):
            set_labeler(labeler)
            clear_labeler()

        self.assertIsInstance(get_labeler(), Labeler)

    def test_get_labeler_attributes_failsafe(self):
        with patch(
            "opentelemetry.instrumentation._labeler._internal.get_value",
            side_effect=RuntimeError("boom"),
        ):
            attrs = get_labeler_attributes()
        self.assertEqual(attrs, {})

    def test_context_key_constant(self):
        self.assertTrue(isinstance(LABELER_CONTEXT_KEY, str))
