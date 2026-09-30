# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import dataclasses
import os
import re
from typing import Any, Literal
from unittest import TestCase
from unittest.mock import patch

from tests._util import assert_logs

from opentelemetry.instrumentation.http.client import (
    HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)

_OPTIONS_FIELDS = tuple(field.name for field in dataclasses.fields(HttpClientTelemetryOptions))
_OPT_IN_FIELDS = ("capture_url_scheme", "capture_network_transport", "capture_user_agent_original")

_ATTRIBUTE_FIELDS = (
    "capture_request_body_size",
    "capture_response_body_size",
    "capture_request_size",
    "capture_response_size",
    "capture_url_template",
)
_METRIC_FIELDS = (
    "enable_request_body_size_metric",
    "enable_response_body_size_metric",
    "enable_open_connections_metric",
    "enable_connection_duration_metric",
    "enable_active_requests_metric",
    "capture_network_peer_address",
)


class TestOptions(TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(
            dataclasses.asdict(HttpClientTelemetryOptions()),
            {
                "captured_request_headers": None,
                "captured_response_headers": None,
                "sanitized_headers": None,
                "capture_network_transport": None,
                "capture_url_scheme": None,
                "capture_user_agent_original": None,
                "known_methods": None,
                "capture_all_methods": None,
                "excluded_urls": None,
            },
        )

    def test_accepts_any_collection(self) -> None:
        options = HttpClientTelemetryOptions(
            captured_request_headers=["content-type"],
            captured_response_headers={"x-request-id"},
            known_methods=frozenset({"GET", "POST"}),
        )

        self.assertEqual(list(options.captured_request_headers), ["content-type"])
        self.assertEqual(set(options.captured_response_headers), {"x-request-id"})
        self.assertEqual(options.known_methods, frozenset({"GET", "POST"}))

    def test_frozen(self) -> None:
        options = HttpClientTelemetryOptions()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(options, "capture_url_scheme", True)

    def test_accepts_strings_and_patterns(self) -> None:
        pattern = re.compile("x-.*")
        options = HttpClientTelemetryOptions(
            captured_request_headers=["content-type", pattern],
            excluded_urls=["https://example.com/health", pattern],
        )

        self.assertEqual(options.captured_request_headers, ["content-type", pattern])
        self.assertEqual(options.excluded_urls, ["https://example.com/health", pattern])


class TestOptionsFromEnv(TestCase):
    _CASES: tuple[tuple[str, str | None, dict[str, str], dict[str, Any], str | None], ...] = (
        ("unset", None, {}, dict.fromkeys(_OPTIONS_FIELDS), None),
        (
            "all variables",
            None,
            {
                "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST": "content-type, x-.*",
                "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE": "x-request-id",
                "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS": "authorization",
                "OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES": "network.transport, url.scheme",
                "OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS": "GET, POST",
                "OTEL_PYTHON_EXCLUDED_URLS": "health,ready",
            },
            {
                "captured_request_headers": (
                    re.compile("content-type", re.IGNORECASE),
                    re.compile("x-.*", re.IGNORECASE),
                ),
                "captured_response_headers": (re.compile("x-request-id", re.IGNORECASE),),
                "sanitized_headers": (re.compile("authorization", re.IGNORECASE),),
                "capture_network_transport": True,
                "capture_url_scheme": True,
                "capture_user_agent_original": False,
                "known_methods": ("GET", "POST"),
                "capture_all_methods": None,
                "excluded_urls": (re.compile("health"), re.compile("ready")),
            },
            None,
        ),
        (
            "invalid values are unset",
            None,
            {"OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST": "content-type,[bad"},
            {"captured_request_headers": None, "capture_all_methods": None},
            "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST",
        ),
        ("opt-in attributes unset", None, {}, dict.fromkeys(_OPT_IN_FIELDS), None),
        (
            "opt-in attributes blank",
            None,
            {"OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES": " "},
            dict.fromkeys(_OPT_IN_FIELDS),
            None,
        ),
        (
            "opt-in attributes all",
            None,
            {"OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES": "*"},
            dict.fromkeys(_OPT_IN_FIELDS, True),
            None,
        ),
        (
            "unlisted opt-in attributes are false",
            None,
            {"OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES": "url.scheme"},
            {"capture_url_scheme": True, "capture_network_transport": False, "capture_user_agent_original": False},
            None,
        ),
        (
            "unknown opt-in attribute is skipped",
            None,
            {"OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES": "url.scheme,url.shceme"},
            {"capture_url_scheme": True, "capture_network_transport": False},
            "url.shceme",
        ),
        (
            "known methods wildcard captures all methods",
            None,
            {"OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS": "*"},
            {"known_methods": None, "capture_all_methods": True},
            None,
        ),
        (
            "capture all methods env var is ignored",
            None,
            {"OTEL_PYTHON_INSTRUMENTATION_HTTP_CAPTURE_ALL_METHODS": "true"},
            {"capture_all_methods": None},
            None,
        ),
        (
            "excluded urls prefer instrumentation-specific",
            "requests",
            {"OTEL_PYTHON_REQUESTS_EXCLUDED_URLS": "specific", "OTEL_PYTHON_EXCLUDED_URLS": "generic"},
            {"excluded_urls": (re.compile("specific"),)},
            None,
        ),
        (
            "excluded urls fall back to generic when specific is unset",
            "REQUESTS",
            {"OTEL_PYTHON_EXCLUDED_URLS": "generic"},
            {"excluded_urls": (re.compile("generic"),)},
            None,
        ),
        *(
            (
                f"excluded urls do not fall back to generic when specific is {specific!r}",
                "REQUESTS",
                {"OTEL_PYTHON_REQUESTS_EXCLUDED_URLS": specific, "OTEL_PYTHON_EXCLUDED_URLS": "generic"},
                {"excluded_urls": None},
                "OTEL_PYTHON_REQUESTS_EXCLUDED_URLS" if specific == "[bad" else None,
            )
            for specific in ("", "  ", "[bad")
        ),
        (
            "excluded urls without name read generic only",
            None,
            {"OTEL_PYTHON_REQUESTS_EXCLUDED_URLS": "specific", "OTEL_PYTHON_EXCLUDED_URLS": "generic"},
            {"excluded_urls": (re.compile("generic"),)},
            None,
        ),
    )

    def test_from_env(self) -> None:
        for case, instrumentation_name, env, expected, warning in self._CASES:
            with (
                self.subTest(case),
                patch.dict(os.environ, env, clear=True),
                assert_logs(self, contains=warning, present=warning is not None),
            ):
                options = HttpClientTelemetryOptions.from_env(instrumentation_name)

                self.assertEqual({field: getattr(options, field) for field in expected}, expected)


class TestOptionsMerge(TestCase):
    def test_other_wins_when_set(self) -> None:
        base = HttpClientTelemetryOptions(capture_url_scheme=True, known_methods=["GET"])
        other = HttpClientTelemetryOptions(capture_url_scheme=False, known_methods=["POST"])

        merged = base.merge(other)

        self.assertIs(merged.capture_url_scheme, False)
        self.assertEqual(merged.known_methods, ["POST"])

    def test_keeps_self_when_other_unset(self) -> None:
        base = HttpClientTelemetryOptions(capture_url_scheme=True, captured_request_headers=["content-type"])

        merged = base.merge(HttpClientTelemetryOptions())

        self.assertEqual(merged, base)
        self.assertIsNot(merged, base)

    def test_collections_are_replaced(self) -> None:
        base = HttpClientTelemetryOptions(captured_request_headers=["content-type"])
        other = HttpClientTelemetryOptions(captured_request_headers=["x-request-id"])

        self.assertEqual(base.merge(other).captured_request_headers, ["x-request-id"])


class TestDevelopmentOptions(TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(
            dataclasses.asdict(HttpClientTelemetryDevelopmentOptions()),
            {
                "capture_request_body_size": None,
                "capture_response_body_size": None,
                "capture_request_size": None,
                "capture_response_size": None,
                "capture_url_template": None,
                "user_agent_synthetic_type_detector": None,
                "capture_request_body_content": None,
                "capture_response_body_content": None,
                "body_content_max_size": None,
                "enable_request_body_size_metric": None,
                "enable_response_body_size_metric": None,
                "enable_open_connections_metric": None,
                "enable_connection_duration_metric": None,
                "enable_active_requests_metric": None,
                "capture_network_peer_address": None,
                "sensitive_query_parameters": None,
                "ignore_cancellation_errors": None,
            },
        )

    def test_accepts_any_collection(self) -> None:
        options = HttpClientTelemetryDevelopmentOptions(sensitive_query_parameters=["sig"])

        self.assertEqual(options.sensitive_query_parameters, ["sig"])

    def test_user_agent_synthetic_type_detector(self) -> None:
        def detector(user_agent: str) -> Literal["bot", "test"] | None:
            return "bot" if "bot" in user_agent else None

        options = HttpClientTelemetryDevelopmentOptions(user_agent_synthetic_type_detector=detector)

        self.assertIs(options.user_agent_synthetic_type_detector, detector)

    def test_frozen(self) -> None:
        options = HttpClientTelemetryDevelopmentOptions()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(options, "capture_url_template", True)

    def test_from_env(self) -> None:
        for case, env, expected, warning in (
            ("unset", {}, HttpClientTelemetryDevelopmentOptions(), None),
            (
                "telemetry",
                {"OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY": "true"},
                HttpClientTelemetryDevelopmentOptions(**dict.fromkeys(_ATTRIBUTE_FIELDS + _METRIC_FIELDS, True)),
                None,
            ),
            (
                "attributes only",
                {"OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_ATTRIBUTES": "true"},
                HttpClientTelemetryDevelopmentOptions(**dict.fromkeys(_ATTRIBUTE_FIELDS, True)),
                None,
            ),
            (
                "metrics only",
                {"OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS": "true"},
                HttpClientTelemetryDevelopmentOptions(**dict.fromkeys(_METRIC_FIELDS, True)),
                None,
            ),
            (
                "specific overrides telemetry",
                {
                    "OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY": "true",
                    "OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_METRICS": "false",
                },
                HttpClientTelemetryDevelopmentOptions(
                    **dict.fromkeys(_ATTRIBUTE_FIELDS, True),
                    **dict.fromkeys(_METRIC_FIELDS, False),
                ),
                None,
            ),
            (
                "invalid values are unset",
                {"OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY": "yes"},
                HttpClientTelemetryDevelopmentOptions(),
                "OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_TELEMETRY",
            ),
        ):
            with (
                self.subTest(case),
                patch.dict(os.environ, env, clear=True),
                assert_logs(self, contains=warning, present=warning is not None),
            ):
                self.assertEqual(HttpClientTelemetryDevelopmentOptions.from_env(), expected)

    def test_merge(self) -> None:
        def detector(user_agent: str) -> Literal["bot", "test"] | None:
            return None

        base = HttpClientTelemetryDevelopmentOptions(
            capture_url_template=True,
            body_content_max_size=1024,
            sensitive_query_parameters=["sig"],
        )
        other = HttpClientTelemetryDevelopmentOptions(
            capture_url_template=False,
            body_content_max_size=0,
            user_agent_synthetic_type_detector=detector,
        )

        merged = base.merge(other)

        self.assertIs(merged.capture_url_template, False)
        self.assertEqual(merged.body_content_max_size, 0)
        self.assertEqual(merged.sensitive_query_parameters, ["sig"])
        self.assertIs(merged.user_agent_synthetic_type_detector, detector)
