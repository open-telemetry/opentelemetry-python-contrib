# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase, mock

from opentelemetry.instrumentation.celery import CeleryGetter


class TestCeleryGetter(TestCase):
    def test_get_none(self):
        getter = CeleryGetter()
        carrier = {}
        val = getter.get(carrier, "test")
        self.assertIsNone(val)

    def test_get_str(self):
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = "val"
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ("val",))

    def test_get_iter(self):
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = ["val"]
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ("val",))

    def test_get_int(self):
        """Non-string scalar values should be coerced to strings.

        Celery's Context stores some attributes as ints (e.g. priority).
        The TextMapPropagator contract requires string values; passing
        an int to re.split() in TraceState.from_header() causes a
        TypeError.
        """
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = 42
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ("42",))

    def test_get_iter_with_non_string_elements(self):
        """Iterable values containing non-strings should be coerced.

        Celery's timelimit attribute is a tuple of ints, e.g. (300, 60).
        """
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = (300, 60)
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ("300", "60"))

    def test_get_iter_with_mixed_types(self):
        """Iterables with a mix of strings and non-strings."""
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = ["val", 123]
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ("val", "123"))

    def test_keys(self):
        getter = CeleryGetter()
        keys = getter.keys({})
        self.assertEqual(keys, [])
