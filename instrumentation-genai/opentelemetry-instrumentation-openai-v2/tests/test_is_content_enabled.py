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

"""Unit tests for is_content_enabled() covering all ContentCapturingMode values."""

import pytest

from opentelemetry.instrumentation.openai_v2.utils import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    is_content_enabled,
)


@pytest.mark.parametrize(
    "env_value",
    ["true", "True", "TRUE"],
)
def test_is_content_enabled_true(monkeypatch, env_value):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, env_value)
    assert is_content_enabled() is True


def test_is_content_enabled_span_and_event(monkeypatch):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "span_and_event")
    assert is_content_enabled() is True


def test_is_content_enabled_span_only(monkeypatch):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "span_only")
    assert is_content_enabled() is True


def test_is_content_enabled_event_only(monkeypatch):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "event_only")
    assert is_content_enabled() is True


@pytest.mark.parametrize(
    "env_value",
    ["false", "False", "FALSE"],
)
def test_is_content_enabled_false(monkeypatch, env_value):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, env_value)
    assert is_content_enabled() is False


def test_is_content_enabled_empty(monkeypatch):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "")
    assert is_content_enabled() is False


def test_is_content_enabled_random_string(monkeypatch):
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "random")
    assert is_content_enabled() is False


def test_is_content_enabled_unset(monkeypatch):
    monkeypatch.delenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, raising=False)
    assert is_content_enabled() is False
