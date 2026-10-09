# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from tests._util import assert_attributes

from opentelemetry.instrumentation.http._internal._http import (
    get_request_size_attributes,
    get_resend_count_attributes,
    get_response_size_attributes,
    get_status_code_attributes,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_RESEND_COUNT,
    HTTP_RESPONSE_STATUS_CODE,
)


class TestGetStatusCodeAttributes(TestCase):
    def test_get_status_code_attributes(self) -> None:
        for status_code, expected in (
            (200, {HTTP_RESPONSE_STATUS_CODE: 200}),
            (404, {HTTP_RESPONSE_STATUS_CODE: 404}),
            (0, {HTTP_RESPONSE_STATUS_CODE: 0}),
            (None, {}),
        ):
            with self.subTest(status_code=status_code):
                assert_attributes(self, get_status_code_attributes(status_code), expected)


class TestGetResendCountAttributes(TestCase):
    def test_get_resend_count_attributes(self) -> None:
        for resend_count, expected in (
            (1, {HTTP_REQUEST_RESEND_COUNT: 1}),
            (3, {HTTP_REQUEST_RESEND_COUNT: 3}),
            (None, {}),
            (0, {}),
        ):
            with self.subTest(resend_count=resend_count):
                assert_attributes(self, get_resend_count_attributes(resend_count), expected)


class TestGetSizeAttributes(TestCase):
    def test_get_size_attributes(self) -> None:
        for get_attributes, body_size, size, capture_body_size, capture_size, expected in (
            (
                get_request_size_attributes,
                10,
                100,
                True,
                True,
                {"http.request.body.size": 10, "http.request.size": 100},
            ),
            (get_request_size_attributes, 10, 100, True, False, {"http.request.body.size": 10}),
            (get_request_size_attributes, 10, 100, False, True, {"http.request.size": 100}),
            (get_request_size_attributes, 10, 100, False, False, {}),
            (get_request_size_attributes, None, None, True, True, {}),
            (
                get_response_size_attributes,
                10,
                100,
                True,
                True,
                {"http.response.body.size": 10, "http.response.size": 100},
            ),
            (get_response_size_attributes, 10, 100, False, False, {}),
            # Zero is recorded.
            (get_response_size_attributes, 0, 0, True, True, {"http.response.body.size": 0, "http.response.size": 0}),
        ):
            with self.subTest(
                get_attributes=get_attributes.__name__,
                body_size=body_size,
                size=size,
                capture_body_size=capture_body_size,
                capture_size=capture_size,
            ):
                assert_attributes(
                    self,
                    get_attributes(body_size, size, capture_body_size=capture_body_size, capture_size=capture_size),
                    expected,
                )
