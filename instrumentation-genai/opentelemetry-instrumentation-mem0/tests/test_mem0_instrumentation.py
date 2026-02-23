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

"""Tests for Mem0 memory operation instrumentation."""

from __future__ import annotations

from unittest import mock

import pytest

from opentelemetry.instrumentation.mem0.patch import (
    GEN_AI_MEMORY_CONTENT,
    GEN_AI_MEMORY_ID,
    GEN_AI_MEMORY_NAMESPACE,
    GEN_AI_MEMORY_QUERY,
    GEN_AI_MEMORY_SCOPE,
    GEN_AI_MEMORY_SEARCH_RESULT_COUNT,
    GEN_AI_OPERATION_NAME,
    GEN_AI_SYSTEM,
    wrap_memory_add,
    wrap_memory_delete,
    wrap_memory_delete_all,
    wrap_memory_get_all,
    wrap_memory_search,
    wrap_memory_update,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import SpanKind, StatusCode


class _InMemoryExporter(SpanExporter):
    def __init__(self):
        self.spans = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def get_finished_spans(self):
        return list(self.spans)


@pytest.fixture()
def tracer_provider():
    provider = TracerProvider()
    return provider


@pytest.fixture()
def exporter(tracer_provider):
    exp = _InMemoryExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exp))
    return exp


def _get_attrs(exporter):
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    return span, {k: v for k, v in span.attributes.items()}


class TestMemoryAdd:
    def test_basic_add(self, tracer_provider, exporter):
        wrapped = mock.Mock(return_value={"results": [{"id": "mem-1"}]})
        wrapper = wrap_memory_add(tracer_provider)
        result = wrapper(
            wrapped, None, ("I like dark mode",), {"user_id": "alice"}
        )

        assert result == {"results": [{"id": "mem-1"}]}
        wrapped.assert_called_once()

        span, attrs = _get_attrs(exporter)
        assert span.name == "update_memory mem0"
        assert span.kind == SpanKind.CLIENT
        assert attrs[GEN_AI_OPERATION_NAME] == "update_memory"
        assert attrs[GEN_AI_SYSTEM] == "mem0"
        assert attrs[GEN_AI_MEMORY_SCOPE] == "user"
        assert attrs[GEN_AI_MEMORY_NAMESPACE] == "user:alice"
        assert attrs[GEN_AI_MEMORY_ID] == "mem-1"

    def test_add_captures_content_when_enabled(
        self, tracer_provider, exporter, monkeypatch
    ):
        monkeypatch.setenv(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true"
        )
        wrapped = mock.Mock(return_value={"results": []})
        wrapper = wrap_memory_add(tracer_provider)
        wrapper(wrapped, None, ("I like dark mode",), {"user_id": "bob"})

        span, attrs = _get_attrs(exporter)
        assert attrs[GEN_AI_MEMORY_CONTENT] == "I like dark mode"

    def test_add_does_not_capture_content_by_default(
        self, tracer_provider, exporter, monkeypatch
    ):
        monkeypatch.delenv(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False
        )
        wrapped = mock.Mock(return_value={"results": []})
        wrapper = wrap_memory_add(tracer_provider)
        wrapper(wrapped, None, ("secret data",), {"user_id": "bob"})

        span, attrs = _get_attrs(exporter)
        assert GEN_AI_MEMORY_CONTENT not in attrs

    def test_add_error_records_exception(self, tracer_provider, exporter):
        wrapped = mock.Mock(side_effect=RuntimeError("db down"))
        wrapper = wrap_memory_add(tracer_provider)

        with pytest.raises(RuntimeError, match="db down"):
            wrapper(wrapped, None, ("data",), {"user_id": "alice"})

        span, _ = _get_attrs(exporter)
        assert span.status.status_code == StatusCode.ERROR


class TestMemorySearch:
    def test_basic_search(self, tracer_provider, exporter):
        wrapped = mock.Mock(
            return_value={"results": [{"id": "r1"}, {"id": "r2"}]}
        )
        wrapper = wrap_memory_search(tracer_provider)
        result = wrapper(wrapped, None, ("preferences",), {"user_id": "alice"})

        assert result == {"results": [{"id": "r1"}, {"id": "r2"}]}

        span, attrs = _get_attrs(exporter)
        assert span.name == "search_memory mem0"
        assert attrs[GEN_AI_OPERATION_NAME] == "search_memory"
        assert attrs[GEN_AI_MEMORY_SEARCH_RESULT_COUNT] == 2
        assert attrs[GEN_AI_MEMORY_SCOPE] == "user"

    def test_search_captures_query_when_enabled(
        self, tracer_provider, exporter, monkeypatch
    ):
        monkeypatch.setenv(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true"
        )
        wrapped = mock.Mock(return_value=[])
        wrapper = wrap_memory_search(tracer_provider)
        wrapper(wrapped, None, ("my query",), {"agent_id": "bot-1"})

        span, attrs = _get_attrs(exporter)
        assert attrs[GEN_AI_MEMORY_QUERY] == "my query"
        assert attrs[GEN_AI_MEMORY_SCOPE] == "agent"

    def test_search_list_result(self, tracer_provider, exporter):
        wrapped = mock.Mock(
            return_value=[{"id": "a"}, {"id": "b"}, {"id": "c"}]
        )
        wrapper = wrap_memory_search(tracer_provider)
        wrapper(wrapped, None, ("q",), {})

        span, attrs = _get_attrs(exporter)
        assert attrs[GEN_AI_MEMORY_SEARCH_RESULT_COUNT] == 3


class TestMemoryUpdate:
    def test_basic_update(self, tracer_provider, exporter):
        wrapped = mock.Mock(return_value={"status": "ok"})
        wrapper = wrap_memory_update(tracer_provider)
        result = wrapper(wrapped, None, ("mem-42",), {"data": "new content"})

        assert result == {"status": "ok"}

        span, attrs = _get_attrs(exporter)
        assert span.name == "update_memory mem0"
        assert attrs[GEN_AI_OPERATION_NAME] == "update_memory"
        assert attrs[GEN_AI_MEMORY_ID] == "mem-42"


class TestMemoryDelete:
    def test_basic_delete(self, tracer_provider, exporter):
        wrapped = mock.Mock(return_value=None)
        wrapper = wrap_memory_delete(tracer_provider)
        wrapper(wrapped, None, ("mem-99",), {})

        span, attrs = _get_attrs(exporter)
        assert span.name == "delete_memory mem0"
        assert attrs[GEN_AI_OPERATION_NAME] == "delete_memory"
        assert attrs[GEN_AI_MEMORY_ID] == "mem-99"


class TestMemoryDeleteAll:
    def test_delete_all_with_user(self, tracer_provider, exporter):
        wrapped = mock.Mock(return_value=None)
        wrapper = wrap_memory_delete_all(tracer_provider)
        wrapper(wrapped, None, (), {"user_id": "alice"})

        span, attrs = _get_attrs(exporter)
        assert span.name == "delete_memory mem0"
        assert attrs[GEN_AI_OPERATION_NAME] == "delete_memory"
        assert attrs[GEN_AI_MEMORY_SCOPE] == "user"


class TestMemoryGetAll:
    def test_get_all(self, tracer_provider, exporter):
        wrapped = mock.Mock(return_value={"results": [{"id": "a"}]})
        wrapper = wrap_memory_get_all(tracer_provider)
        wrapper(wrapped, None, (), {"user_id": "alice"})

        span, attrs = _get_attrs(exporter)
        assert span.name == "search_memory mem0"
        assert attrs[GEN_AI_OPERATION_NAME] == "search_memory"
        assert attrs[GEN_AI_MEMORY_SEARCH_RESULT_COUNT] == 1
