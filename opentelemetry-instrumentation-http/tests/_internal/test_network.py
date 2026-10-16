# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from tests._util import assert_attributes

from opentelemetry.instrumentation.http._internal._network import (
    get_peer_attributes,
    get_protocol_attributes,
    get_transport_attributes,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
    NETWORK_PROTOCOL_NAME,
    NETWORK_PROTOCOL_VERSION,
    NETWORK_TRANSPORT,
)


class TestGetProtocolAttributes(TestCase):
    def test_get_protocol_attributes(self) -> None:
        for name, version, expected in (
            (None, "1.1", {NETWORK_PROTOCOL_VERSION: "1.1"}),
            # HTTP and HTTPS names are omitted.
            ("http", "2", {NETWORK_PROTOCOL_VERSION: "2"}),
            ("HTTP", "2", {NETWORK_PROTOCOL_VERSION: "2"}),
            ("https", "2", {NETWORK_PROTOCOL_VERSION: "2"}),
            ("HTTPS", "2", {NETWORK_PROTOCOL_VERSION: "2"}),
            # Other names are lowercased.
            ("SPDY", "3", {NETWORK_PROTOCOL_NAME: "spdy", NETWORK_PROTOCOL_VERSION: "3"}),
            # The version is recorded as given.
            (None, "HTTP/2.0", {NETWORK_PROTOCOL_VERSION: "HTTP/2.0"}),
            # Nothing is recorded without a version.
            ("spdy", None, {}),
            ("spdy", "", {}),
        ):
            with self.subTest(name=name, version=version):
                assert_attributes(self, get_protocol_attributes(name, version), expected)


class TestGetPeerAttributes(TestCase):
    def test_get_peer_attributes(self) -> None:
        for address, port, expected in (
            ("10.1.2.80", 65123, {NETWORK_PEER_ADDRESS: "10.1.2.80", NETWORK_PEER_PORT: 65123}),
            ("/tmp/my.sock", None, {NETWORK_PEER_ADDRESS: "/tmp/my.sock"}),
            # The port is not recorded without an address.
            (None, 65123, {}),
            ("", 65123, {}),
        ):
            with self.subTest(address=address, port=port):
                assert_attributes(self, get_peer_attributes(address, port), expected)


class TestGetTransportAttributes(TestCase):
    def test_get_transport_attributes(self) -> None:
        for transport, expected in (
            ("tcp", {NETWORK_TRANSPORT: "tcp"}),
            (None, {}),
        ):
            with self.subTest(transport=transport):
                assert_attributes(self, get_transport_attributes(transport), expected)
