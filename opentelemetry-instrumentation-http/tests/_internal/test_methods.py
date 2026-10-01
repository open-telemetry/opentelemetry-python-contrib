# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry.instrumentation.http._internal._methods import (
    get_known_methods,
    get_method_attributes,
    get_span_name,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_REQUEST_METHOD_ORIGINAL,
)

_DEFAULT_METHODS = frozenset({"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "QUERY", "TRACE"})
_GET = frozenset({"GET"})


class TestGetKnownMethods(TestCase):
    def test_get_known_methods(self) -> None:
        for known_methods, expected in (
            (None, _DEFAULT_METHODS),
            # Known methods replace the default.
            (["FOO", "GET"], frozenset({"FOO", "GET"})),
            ([], frozenset()),
        ):
            with self.subTest(known_methods=known_methods):
                self.assertEqual(get_known_methods(known_methods), expected)


class TestGetMethodAttributes(TestCase):
    def test_get_method_attributes(self) -> None:
        for method, known_methods, expected in (
            ("GET", _DEFAULT_METHODS, {HTTP_REQUEST_METHOD: "GET"}),
            # Unknown methods are case-sensitive.
            ("FOO", _DEFAULT_METHODS, {HTTP_REQUEST_METHOD: "_OTHER", HTTP_REQUEST_METHOD_ORIGINAL: "FOO"}),
            ("get", _DEFAULT_METHODS, {HTTP_REQUEST_METHOD: "_OTHER", HTTP_REQUEST_METHOD_ORIGINAL: "get"}),
            ("GeT", _DEFAULT_METHODS, {HTTP_REQUEST_METHOD: "_OTHER", HTTP_REQUEST_METHOD_ORIGINAL: "GeT"}),
            # _OTHER has no original method.
            ("_OTHER", _DEFAULT_METHODS, {HTTP_REQUEST_METHOD: "_OTHER"}),
            # All methods are known.
            ("FOO", None, {HTTP_REQUEST_METHOD: "FOO"}),
        ):
            with self.subTest(method=method, known_methods=known_methods):
                self.assertEqual(get_method_attributes(method, known_methods), expected)


class TestGetSpanName(TestCase):
    def test_get_span_name(self) -> None:
        for method, known_methods, target, expected in (
            ("GET", _GET, None, "GET"),
            ("FOO", _GET, None, "HTTP"),
            ("get", _GET, None, "HTTP"),
            # All methods are known.
            ("FOO", None, None, "FOO"),
            ("GET", _GET, "/users/{id}", "GET /users/{id}"),
            ("FOO", _GET, "/users/{id}", "HTTP /users/{id}"),
            ("GET", _GET, "", "GET"),
        ):
            with self.subTest(method=method, known_methods=known_methods, target=target):
                self.assertEqual(get_span_name(method, known_methods, target), expected)
