# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase
from urllib.parse import urlsplit

from tests._util import assert_attributes

from opentelemetry.instrumentation.http._internal._server import (
    get_server_attributes,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)


class TestGetServerAttributes(TestCase):
    def test_get_server_attributes(self) -> None:
        for url, address, port, expected in (
            ("https://example.com:8443/path", None, None, {SERVER_ADDRESS: "example.com", SERVER_PORT: 8443}),
            # Default ports.
            ("https://example.com/", None, None, {SERVER_ADDRESS: "example.com", SERVER_PORT: 443}),
            ("http://example.com/", None, None, {SERVER_ADDRESS: "example.com", SERVER_PORT: 80}),
            ("HTTPS://example.com", None, None, {SERVER_ADDRESS: "example.com", SERVER_PORT: 443}),
            ("ftp://example.com/", None, None, {SERVER_ADDRESS: "example.com"}),
            # The hostname is normalized.
            ("https://user:pass@Example.COM/", None, None, {SERVER_ADDRESS: "example.com", SERVER_PORT: 443}),
            ("http://[::1]:8080/", None, None, {SERVER_ADDRESS: "::1", SERVER_PORT: 8080}),
            ("http://example.com:abc/", None, None, {SERVER_ADDRESS: "example.com"}),
            # No host.
            ("/path", None, None, {}),
            (None, None, None, {}),
            # Explicit address and port.
            ("https://proxy.local:3128/", "Example.com", 8443, {SERVER_ADDRESS: "Example.com", SERVER_PORT: 8443}),
            ("https://proxy.local:3128/", "example.com", None, {SERVER_ADDRESS: "example.com", SERVER_PORT: 443}),
            (None, "example.com", None, {SERVER_ADDRESS: "example.com"}),
            ("/path", "/tmp/my.sock", None, {SERVER_ADDRESS: "/tmp/my.sock"}),
            # An explicit port without an address is ignored.
            ("https://example.com:8443/", None, 9999, {SERVER_ADDRESS: "example.com", SERVER_PORT: 8443}),
            ("/path", None, 9999, {}),
        ):
            with self.subTest(url=url, address=address, port=port):
                parts = urlsplit(url) if url is not None else None

                assert_attributes(self, get_server_attributes(parts, address, port), expected)
