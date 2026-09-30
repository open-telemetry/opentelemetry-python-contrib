# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from tests._util import RecordingSampler

from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_FULL,
    URL_SCHEME,
)
from opentelemetry.test.test_base import TestBase

_BASE_ATTRIBUTES = {HTTP_REQUEST_METHOD: "GET", SERVER_ADDRESS: "example.com", SERVER_PORT: 443}


class TestHttpClientTelemetryUrlAttributes(TestBase):
    def _attributes(
        self,
        request: HttpClientRequest,
        options: HttpClientTelemetryOptions | None = None,
        development_options: HttpClientTelemetryDevelopmentOptions | None = None,
    ) -> dict[str, Any]:
        HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            options=options,
            development_options=development_options,
        ).start(request).end()
        (span,) = self.get_finished_spans()
        return dict(span.attributes or {})

    def test_url_full_is_redacted(self) -> None:
        attributes = self._attributes(
            HttpClientRequest(method="GET", url="https://user:pass@example.com/path?sig=secret&color=blue#top")
        )

        self.assertEqual(
            attributes,
            {**_BASE_ATTRIBUTES, URL_FULL: "https://REDACTED:REDACTED@example.com/path?sig=REDACTED&color=blue#top"},
        )
        self.assertIsInstance(attributes[URL_FULL], str)

    def test_opt_in_attributes(self) -> None:
        attributes = self._attributes(
            HttpClientRequest(method="GET", url="https://example.com/users/1", url_template="/users/{id}"),
            HttpClientTelemetryOptions(capture_url_scheme=True),
            HttpClientTelemetryDevelopmentOptions(capture_url_template=True),
        )

        self.assertEqual(
            attributes,
            {
                **_BASE_ATTRIBUTES,
                URL_FULL: "https://example.com/users/1",
                URL_SCHEME: "https",
                "url.template": "/users/{id}",
            },
        )

    def test_sensitive_query_parameters_option(self) -> None:
        attributes = self._attributes(
            HttpClientRequest(method="GET", url="https://example.com/?token=secret&sig=1"),
            development_options=HttpClientTelemetryDevelopmentOptions(sensitive_query_parameters=["token"]),
        )

        self.assertEqual(attributes, {**_BASE_ATTRIBUTES, URL_FULL: "https://example.com/?token=REDACTED&sig=1"})

    def test_url_attributes_are_available_to_sampler(self) -> None:
        sampler = RecordingSampler()
        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=TracerProvider(sampler=sampler),
            options=HttpClientTelemetryOptions(capture_url_scheme=True),
        )

        telemetry.start(HttpClientRequest(method="GET", url="https://example.com/?sig=1")).end()

        self.assertEqual(
            sampler.attributes,
            [{**_BASE_ATTRIBUTES, URL_FULL: "https://example.com/?sig=REDACTED", URL_SCHEME: "https"}],
        )
