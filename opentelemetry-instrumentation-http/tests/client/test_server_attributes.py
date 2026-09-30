# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from tests._util import RecordingSampler, assert_attributes

from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientTelemetry,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase


class TestHttpClientTelemetryServerAttributes(TestBase):
    def _server_attributes(self, request: HttpClientRequest) -> dict[str, Any]:
        HttpClientTelemetry(instrumenting_module_name="test", tracer_provider=self.tracer_provider).start(request).end()
        (span,) = self.get_finished_spans()
        self.memory_exporter.clear()
        return {key: value for key, value in (span.attributes or {}).items() if key.startswith("server.")}

    def test_attributes(self) -> None:
        for case, request, expected in (
            (
                "from url",
                HttpClientRequest(method="GET", url="http://Example.com:8080/path"),
                {SERVER_ADDRESS: "example.com", SERVER_PORT: 8080},
            ),
            (
                "default port",
                HttpClientRequest(method="GET", url="https://example.com/path"),
                {SERVER_ADDRESS: "example.com", SERVER_PORT: 443},
            ),
            (
                "explicit fields",
                HttpClientRequest(
                    method="GET", url="http://proxy.local:3128/path", server_address="example.com", server_port=8443
                ),
                {SERVER_ADDRESS: "example.com", SERVER_PORT: 8443},
            ),
            (
                "unparseable url with explicit address",
                HttpClientRequest(method="GET", url="http://[::1", server_address="::1"),
                {SERVER_ADDRESS: "::1"},
            ),
            ("relative url without explicit address", HttpClientRequest(method="GET", url="/path"), {}),
        ):
            with self.subTest(case):
                assert_attributes(self, self._server_attributes(request), expected)

    def test_server_attributes_are_available_to_sampler(self) -> None:
        sampler = RecordingSampler()
        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test", tracer_provider=TracerProvider(sampler=sampler)
        )

        telemetry.start(HttpClientRequest(method="GET", url="https://example.com:8443/")).end()

        self.assertEqual(len(sampler.attributes), 1)
        self.assertEqual(sampler.attributes[0][SERVER_ADDRESS], "example.com")
        self.assertEqual(sampler.attributes[0][SERVER_PORT], 8443)
