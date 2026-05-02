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

from unittest import TestCase, mock

from opentelemetry.instrumentation.celery import CeleryGetter


class TestCeleryGetter(TestCase):
    def test_get_none(self):
        """Missing attribute on carrier should return None."""
        getter = CeleryGetter()
        carrier = {}
        val = getter.get(carrier, "test")
        self.assertIsNone(val)

    def test_get_str(self):
        """String attribute should be wrapped in a single-element list."""
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = "val"
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ["val"])

    def test_get_iter(self):
        """Iterable attribute should be returned as a list."""
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = ["val"]
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ["val"])

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
        self.assertEqual(val, ["42"])

    def test_get_iter_with_non_string_elements(self):
        """Iterable values containing non-strings should be coerced.

        Celery's timelimit attribute is a tuple of ints, e.g. (300, 60).
        """
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = (300, 60)
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ["300", "60"])

    def test_get_iter_with_mixed_types(self):
        """Iterables with a mix of strings and non-strings."""
        mock_obj = mock.Mock()
        getter = CeleryGetter()
        mock_obj.test = ["val", 123]
        val = getter.get(mock_obj, "test")
        self.assertEqual(val, ["val", "123"])

    def test_get_non_str_non_iterable(self):
        """Non-string, non-iterable value should be coerced to [str(value)]."""
        getter = CeleryGetter()
        mock_obj = mock.Mock()
        mock_obj.key = 42
        val = getter.get(mock_obj, "key")
        self.assertEqual(val, ["42"])

    def test_keys(self):
        """keys() should return an empty list for any carrier."""
        getter = CeleryGetter()
        keys = getter.keys({})
        self.assertEqual(keys, [])
