# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from tests._util import CaseInsensitiveHeaders, RecordingSampler, assert_attributes, assert_logs

from opentelemetry.instrumentation.http.client import (
    HttpClientRequest,
    HttpClientTelemetry,
    HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.attributes.user_agent_attributes import USER_AGENT_ORIGINAL
from opentelemetry.test.test_base import TestBase

_URL = "https://example.com"
_USER_AGENT_SYNTHETIC_TYPE = "user_agent.synthetic.type"
_CAPTURE_OPTIONS = HttpClientTelemetryOptions(capture_user_agent_original=True)


def _detect_bot(user_agent: str) -> Literal["bot", "test"] | None:
    return "bot" if "bot" in user_agent.lower() else None


def _raise(user_agent: str) -> Literal["bot", "test"] | None:
    raise ValueError(user_agent)


_DETECT_BOT_OPTIONS = HttpClientTelemetryDevelopmentOptions(user_agent_synthetic_type_detector=_detect_bot)


class TestHttpClientTelemetryUserAgent(TestBase):
    def _user_agent_attributes(
        self,
        user_agent: str | None = None,
        headers: Mapping[str, str | Sequence[str]] | None = None,
        options: HttpClientTelemetryOptions | None = None,
        development_options: HttpClientTelemetryDevelopmentOptions | None = None,
    ) -> dict[str, Any]:
        HttpClientTelemetry(
            instrumenting_module_name="test",
            tracer_provider=self.tracer_provider,
            options=options,
            development_options=development_options,
        ).start(HttpClientRequest(method="GET", url=_URL, user_agent=user_agent, headers=headers)).end()
        (span,) = self.get_finished_spans()
        self.memory_exporter.clear()
        return {key: value for key, value in (span.attributes or {}).items() if key.startswith("user_agent.")}

    def test_attributes(self) -> None:
        for case, user_agent, headers, options, development_options, expected in (
            ("user_agent.original is opt-in", "curl/8.0", None, None, None, {}),
            ("user_agent.original", "curl/8.0", None, _CAPTURE_OPTIONS, None, {USER_AGENT_ORIGINAL: "curl/8.0"}),
            (
                "from header",
                None,
                {"user-agent": "curl/8.0"},
                _CAPTURE_OPTIONS,
                None,
                {USER_AGENT_ORIGINAL: "curl/8.0"},
            ),
            (
                "from multi-value header",
                None,
                {"user-agent": ["curl/8.0", "other/1.0"]},
                _CAPTURE_OPTIONS,
                None,
                {USER_AGENT_ORIGINAL: "curl/8.0"},
            ),
            (
                "from case-insensitive header",
                None,
                CaseInsensitiveHeaders({"User-Agent": "curl/8.0"}),
                _CAPTURE_OPTIONS,
                None,
                {USER_AGENT_ORIGINAL: "curl/8.0"},
            ),
            (
                "explicit user agent takes precedence over header",
                "curl/8.0",
                {"user-agent": "other/1.0"},
                _CAPTURE_OPTIONS,
                None,
                {USER_AGENT_ORIGINAL: "curl/8.0"},
            ),
            ("no headers", "", None, _CAPTURE_OPTIONS, None, {}),
            ("empty headers", "", {}, _CAPTURE_OPTIONS, None, {}),
            ("no user-agent header", "", {"Accept": "*/*"}, _CAPTURE_OPTIONS, None, {}),
            ("empty user-agent header", "", {"user-agent": ""}, _CAPTURE_OPTIONS, None, {}),
            ("empty multi-value user-agent header", "", {"user-agent": []}, _CAPTURE_OPTIONS, None, {}),
            (
                "synthetic type",
                None,
                {"user-agent": "Googlebot/2.1"},
                None,
                _DETECT_BOT_OPTIONS,
                {_USER_AGENT_SYNTHETIC_TYPE: "bot"},
            ),
            (
                "synthetic type with user_agent.original",
                "Googlebot/2.1",
                None,
                _CAPTURE_OPTIONS,
                _DETECT_BOT_OPTIONS,
                {USER_AGENT_ORIGINAL: "Googlebot/2.1", _USER_AGENT_SYNTHETIC_TYPE: "bot"},
            ),
            ("synthetic type for genuine traffic", "curl/8.0", None, None, _DETECT_BOT_OPTIONS, {}),
        ):
            with self.subTest(case):
                assert_attributes(
                    self,
                    self._user_agent_attributes(
                        user_agent=user_agent,
                        headers=headers,
                        options=options,
                        development_options=development_options,
                    ),
                    expected,
                )

    def test_user_agent_original_is_available_to_sampler(self) -> None:
        sampler = RecordingSampler()
        telemetry = HttpClientTelemetry(
            instrumenting_module_name="test", tracer_provider=TracerProvider(sampler=sampler), options=_CAPTURE_OPTIONS
        )

        telemetry.start(HttpClientRequest(method="GET", url=_URL, user_agent="curl/8.0")).end()

        self.assertEqual(sampler.attributes[0][USER_AGENT_ORIGINAL], "curl/8.0")

    def test_synthetic_type_without_user_agent_skips_detector(self) -> None:
        calls: list[str] = []

        def detector(user_agent: str) -> Literal["bot", "test"] | None:
            calls.append(user_agent)
            return "test"

        attributes = self._user_agent_attributes(
            development_options=HttpClientTelemetryDevelopmentOptions(user_agent_synthetic_type_detector=detector)
        )

        self.assertEqual(attributes, {})
        self.assertEqual(calls, [])

    def test_synthetic_type_detector_exception_is_logged(self) -> None:
        with assert_logs(self, contains="synthetic type detector"):
            attributes = self._user_agent_attributes(
                user_agent="curl/8.0",
                options=_CAPTURE_OPTIONS,
                development_options=HttpClientTelemetryDevelopmentOptions(user_agent_synthetic_type_detector=_raise),
            )

        self.assertEqual(attributes, {USER_AGENT_ORIGINAL: "curl/8.0"})
