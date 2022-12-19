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

from opentelemetry.instrumentation.asgi import ASGIGetter


class TestASGIGetter(TestCase):
    def test_get_none(self):
        getter = ASGIGetter()
        carrier = {}
        val = getter.get(carrier, "test")
        self.assertIsNone(val)

    def test_get_(self):
        getter = ASGIGetter()
        carrier = {"headers": [(b"test-key", b"val")]}
        expected_val = ["val"]
        self.assertEqual(
            getter.get(carrier, "Test-Key"),
            expected_val,
            "Should be case insensitive",
        )
        self.assertEqual(
            getter.get(carrier, "test-key"),
            expected_val,
            "Should be case insensitive",
        )
        self.assertEqual(
            getter.get(carrier, "TEST-KEY"),
            expected_val,
            "Should be case insensitive",
        )

    def test_keys(self):
        getter = ASGIGetter()
        keys = getter.keys({})
        self.assertEqual(keys, [])
        
    def test_populated_keys(self):
        getter = ASGIGetter()
        header = {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"Content-Type", b"text/plain"),
                (b"custom-test-header-1", b"test-header-value-1"),
                (b"custom-test-header-2", b"test-header-value-2"),
                (
                    b"my-custom-regex-header-1",
                    b"my-custom-regex-value-1,my-custom-regex-value-2",
                ),
                (
                    b"My-Custom-Regex-Header-2",
                    b"my-custom-regex-value-3,my-custom-regex-value-4",
                ),
                (b"my-secret-header", b"my-secret-value"),
            ],
            }
        
        expected_val = ['type','status','Content-Type', 'custom-test-header-1', 'custom-test-header-2', 'my-custom-regex-header-1', 'My-Custom-Regex-Header-2', 'my-secret-header']
        keys = getter.keys(header)
        self.assertEqual(keys, expected_val)