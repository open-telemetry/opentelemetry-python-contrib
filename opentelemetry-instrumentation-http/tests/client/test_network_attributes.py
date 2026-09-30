# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from tests._util import assert_attributes

from opentelemetry.instrumentation.http.client import (
    HttpClientConnectionInfo,
    HttpClientRequest,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
    NETWORK_PROTOCOL_NAME,
    NETWORK_PROTOCOL_VERSION,
    NETWORK_TRANSPORT,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import URL_FULL, URL_SCHEME
from opentelemetry.test.test_base import TestBase

_URL = "https://example.com"


def _connection(**kwargs: Any) -> HttpClientConnectionInfo:
    return HttpClientConnectionInfo(server_address="example.com", **kwargs)


class TestHttpClientTelemetryNetworkAttributes(TestBase):
    def _telemetry(self, options: HttpClientTelemetryOptions | None = None) -> HttpClientTelemetry:
        return HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            options=options,
        )

    def _set_connections(
        self,
        *connections: HttpClientConnectionInfo,
        options: HttpClientTelemetryOptions | None = None,
    ) -> dict[str, Any]:
        operation = self._telemetry(options).start(HttpClientRequest(method="GET", url=_URL))
        for connection in connections:
            operation.set_connection(connection)
        operation.end()
        (span,) = self.get_finished_spans()
        self.memory_exporter.clear()
        return {key: value for key, value in (span.attributes or {}).items() if key.startswith("network.")}

    def test_attributes(self) -> None:
        for case, options, connections, expected in (
            (
                "all attributes",
                HttpClientTelemetryOptions(capture_network_transport=True),
                (
                    _connection(
                        network_peer_address="10.1.2.80",
                        network_peer_port=65123,
                        network_protocol_name="SPDY",
                        network_protocol_version="3",
                        network_transport="tcp",
                    ),
                ),
                {
                    NETWORK_PEER_ADDRESS: "10.1.2.80",
                    NETWORK_PEER_PORT: 65123,
                    NETWORK_PROTOCOL_NAME: "spdy",
                    NETWORK_PROTOCOL_VERSION: "3",
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            ("network transport is opt-in", None, (_connection(network_transport="tcp"),), {}),
            (
                "peer address only",
                None,
                (_connection(network_peer_address="/tmp/my.sock"),),
                {NETWORK_PEER_ADDRESS: "/tmp/my.sock"},
            ),
            ("peer port without address", None, (_connection(network_peer_port=65123),), {}),
            (
                "http protocol name is omitted",
                None,
                (_connection(network_protocol_name="http", network_protocol_version="2"),),
                {NETWORK_PROTOCOL_VERSION: "2"},
            ),
            (
                "https protocol name is omitted",
                None,
                (_connection(network_protocol_name="HTTPS", network_protocol_version="2"),),
                {NETWORK_PROTOCOL_VERSION: "2"},
            ),
            ("protocol name without version", None, (_connection(network_protocol_name="spdy"),), {}),
            (
                "last call wins",
                None,
                (
                    _connection(
                        network_peer_address="10.1.2.80", network_peer_port=65123, network_protocol_version="1.1"
                    ),
                    _connection(network_peer_address="10.1.2.81", network_peer_port=443),
                ),
                {NETWORK_PEER_ADDRESS: "10.1.2.81", NETWORK_PEER_PORT: 443, NETWORK_PROTOCOL_VERSION: "1.1"},
            ),
        ):
            with self.subTest(case):
                assert_attributes(self, self._set_connections(*connections, options=options), expected)

    def test_server_and_scheme_are_ignored(self) -> None:
        operation = self._telemetry(HttpClientTelemetryOptions(capture_url_scheme=True)).start(
            HttpClientRequest(method="GET", url=_URL)
        )
        operation.set_connection(
            HttpClientConnectionInfo(server_address="proxy.local", server_port=3128, url_scheme="http")
        )
        operation.end()

        (span,) = self.get_finished_spans()
        self.assertEqual(
            dict(span.attributes or {}),
            {
                HTTP_REQUEST_METHOD: "GET",
                URL_FULL: _URL,
                URL_SCHEME: "https",
                SERVER_ADDRESS: "example.com",
                SERVER_PORT: 443,
            },
        )

    def test_after_end_records_nothing(self) -> None:
        operation = self._telemetry().start(HttpClientRequest(method="GET", url=_URL))
        operation.end()

        operation.set_connection(_connection(network_peer_address="10.1.2.80", network_protocol_version="2"))

        (span,) = self.get_finished_spans()
        self.assertEqual(
            dict(span.attributes or {}),
            {HTTP_REQUEST_METHOD: "GET", URL_FULL: _URL, SERVER_ADDRESS: "example.com", SERVER_PORT: 443},
        )

    def test_skipped_operation(self) -> None:
        operation = self._telemetry(HttpClientTelemetryOptions(excluded_urls=[_URL])).start(
            HttpClientRequest(method="GET", url=_URL)
        )

        operation.set_connection(_connection(network_peer_address="10.1.2.80", network_protocol_version="2"))
        operation.end()

        self.assertFalse(operation.span.is_recording())
        self.assertEqual(self.get_finished_spans(), [])
