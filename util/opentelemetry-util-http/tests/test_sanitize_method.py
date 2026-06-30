# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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
