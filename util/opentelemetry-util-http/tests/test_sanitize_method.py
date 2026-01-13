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
from unittest.mock import patch

from opentelemetry.util.http import (
    OTEL_PYTHON_INSTRUMENTATION_HTTP_CAPTURE_ALL_METHODS,
    sanitize_method,
)


class TestSanitizeMethod(unittest.TestCase):
    def test_standard_method_uppercase(self):
        method = sanitize_method("GET")
        self.assertEqual(method, "GET")

    def test_standard_method_lowercase(self):
        method = sanitize_method("get")
        self.assertEqual(method, "GET")

    def test_nonstandard_method(self):
        method = sanitize_method("UNKNOWN")
        self.assertEqual(method, "_OTHER")

    @patch.dict(
        "os.environ",
        {
            OTEL_PYTHON_INSTRUMENTATION_HTTP_CAPTURE_ALL_METHODS: "1",
        },
    )
    def test_nonstandard_method_allowed(self):
        method = sanitize_method("UNKNOWN")
        self.assertEqual(method, "UNKNOWN")
