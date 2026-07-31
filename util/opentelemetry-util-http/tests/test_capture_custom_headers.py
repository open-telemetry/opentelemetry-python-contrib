# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest.mock import patch

from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    SanitizeValue,
    get_custom_headers,
    normalise_request_header_name,
    normalise_response_header_name,
)


class TestCaptureCustomHeaders(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "User-Agent,Test-Header"
        },
    )
    def test_get_custom_request_header(self):
        custom_headers_to_capture = get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST
        )
        self.assertEqual(
            custom_headers_to_capture, ["User-Agent", "Test-Header"]
        )

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,test-header"
        },
    )
    def test_get_custom_response_header(self):
        custom_headers_to_capture = get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE
        )
        self.assertEqual(
            custom_headers_to_capture,
            [
                "content-type",
                "content-length",
                "test-header",
            ],
        )

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: "My-Secret-Header,My-Secret-Header-2"
        },
    )
    def test_get_custom_sanitize_header(self):
        sanitized_fields = get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS
        )
        self.assertEqual(
            sanitized_fields,
            ["My-Secret-Header", "My-Secret-Header-2"],
        )

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: "My-Secret-Header,My-Secret-Header-2"
        },
    )
    def test_sanitize(self):
        sanitized_fields = get_custom_headers(
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS
        )

        sanitize = SanitizeValue(sanitized_fields)

        self.assertEqual(
            sanitize.sanitize_header_value(
                header="My-Secret-Header", value="My-Secret-Value"
            ),
            "[REDACTED]",
        )

        self.assertEqual(
            sanitize.sanitize_header_value(
                header="My-Not-Secret-Header", value="My-Not-Secret-Value"
            ),
            "My-Not-Secret-Value",
        )

    def test_normalise_request_header_name(self):
        key = normalise_request_header_name("Test-Header")
        self.assertEqual(key, "http.request.header.test_header")

    def test_normalise_response_header_name(self):
        key = normalise_response_header_name("Test-Header")
        self.assertEqual(key, "http.response.header.test_header")
