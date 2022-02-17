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

from unittest.mock import patch

from opentelemetry.test.test_base import TestBase
from opentelemetry.util.http import (
    OTEL_PYTHON_CAPTURE_REQUEST_HEADERS,
    OTEL_PYTHON_CAPTURE_RESPONSE_HEADERS,
    get_custom_headers,
    normalise_request_header_name,
    normalise_response_header_name,
)


class TestCaptureCustomHeaders(TestBase):
    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_CAPTURE_REQUEST_HEADERS: "User-Agent,Test-Header"},
    )
    def test_get_custom_request_header(self):
        custom_headers_to_capture = get_custom_headers(
            OTEL_PYTHON_CAPTURE_REQUEST_HEADERS
        )
        assert custom_headers_to_capture == ["User-Agent", "Test-Header"]

    @patch.dict(
        "os.environ",
        {
            OTEL_PYTHON_CAPTURE_RESPONSE_HEADERS: "content-type,content-length,test-header"
        },
    )
    def test_get_custom_response_header(self):
        custom_headers_to_capture = get_custom_headers(
            OTEL_PYTHON_CAPTURE_RESPONSE_HEADERS
        )
        assert custom_headers_to_capture == [
            "content-type",
            "content-length",
            "test-header",
        ]

    def test_normalise_request_header_name(self):
        key = normalise_request_header_name("Test-Header")
        assert key == "http.request.header.test_header"

    def test_normalise_response_header_name(self):
        key = normalise_response_header_name("Test-Header")
        assert key == "http.response.header.test_header"
