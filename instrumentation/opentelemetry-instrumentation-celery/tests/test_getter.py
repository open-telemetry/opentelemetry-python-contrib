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

from unittest import TestCase

from opentelemetry.instrumentation.celery import _CeleryCustomGetDictionary


class TestCeleryCustomGetDictionary(TestCase):
    def test_get_none(self):
        self.assertIsNone(_CeleryCustomGetDictionary({}).get("test"))

    def test_get_str(self):
        self.assertEqual(
            _CeleryCustomGetDictionary({"test": "val"}).get("test"), "val"
        )

    def test_get_iter(self):
        self.assertEqual(
            _CeleryCustomGetDictionary({"test": ["val"]}).get("test"), ["val"]
        )
