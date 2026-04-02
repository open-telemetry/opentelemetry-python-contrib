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

"""Unit tests for on_retriever_start / on_retriever_end / on_retriever_error callbacks."""

from __future__ import annotations

import json
from unittest import mock
from uuid import uuid4

import pytest

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.semconv_attributes import (
    OP_EXECUTE_TOOL,
)
from opentelemetry.instrumentation.langchain.span_manager import (
    SpanRecord,
    _SpanManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def _make_mock_span():
    """Create a mock span with the interface used by the callback handler."""
    span = mock.MagicMock()
    span.is_recording.return_value = True
    span.set_attribute = mock.MagicMock()
    span.set_status = mock.MagicMock()
    return span


def _make_span_record(
    run_id, span=None, operation=OP_EXECUTE_TOOL, attributes=None
):
    return SpanRecord(
        run_id=str(run_id),
        span=span or _make_mock_span(),
        operation=operation,
        attributes=attributes or {},
    )


@pytest.fixture
def mock_span_manager():
    mgr = mock.MagicMock(spec=_SpanManager)
    mgr.is_ignored.return_value = False
    mgr.start_span.return_value = _make_span_record(uuid4())
    return mgr


@pytest.fixture
def handler(mock_span_manager):
    telemetry_handler = mock.MagicMock()
    return OpenTelemetryLangChainCallbackHandler(
        telemetry_handler=telemetry_handler,
        span_manager=mock_span_manager,
    )


# ---------------------------------------------------------------------------
# on_retriever_start
# ---------------------------------------------------------------------------


class TestOnRetrieverStart:
    """on_retriever_start creates execute_tool spans for retrievers."""

    def test_creates_execute_tool_span_with_retriever_type(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_retriever_start(
            serialized={"name": "vector_store"},
            query="What is OpenTelemetry?",
            run_id=run_id,
        )

        mock_span_manager.start_span.assert_called_once()
        call_kwargs = mock_span_manager.start_span.call_args.kwargs
        assert call_kwargs["operation"] == OP_EXECUTE_TOOL
        assert call_kwargs["kind"] == SpanKind.INTERNAL
        assert call_kwargs["name"] == f"{OP_EXECUTE_TOOL} vector_store"
        attrs = call_kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_OPERATION_NAME] == OP_EXECUTE_TOOL
        assert attrs[GenAI.GEN_AI_TOOL_NAME] == "vector_store"
        assert attrs[GenAI.GEN_AI_TOOL_TYPE] == "retriever"

    def test_sets_query_when_content_recording_enabled(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        with mock.patch(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_retriever_content",
            return_value=True,
        ):
            handler.on_retriever_start(
                serialized={"name": "retriever"},
                query="semantic search query",
                run_id=run_id,
            )

        call_kwargs = mock_span_manager.start_span.call_args.kwargs
        assert (
            call_kwargs["attributes"]["gen_ai.retrieval.query.text"]
            == "semantic search query"
        )

    def test_redacts_query_when_content_recording_disabled(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        with mock.patch(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_retriever_content",
            return_value=False,
        ):
            handler.on_retriever_start(
                serialized={"name": "retriever"},
                query="secret query",
                run_id=run_id,
            )

        call_kwargs = mock_span_manager.start_span.call_args.kwargs
        assert "gen_ai.retrieval.query.text" not in call_kwargs["attributes"]

    def test_inherits_provider_from_parent_span(
        self, handler, mock_span_manager
    ):
        parent_run_id = uuid4()
        run_id = uuid4()
        parent_record = _make_span_record(
            parent_run_id,
            attributes={GenAI.GEN_AI_PROVIDER_NAME: "openai"},
        )
        mock_span_manager.get_record.return_value = parent_record

        handler.on_retriever_start(
            serialized={"name": "retriever"},
            query="test query",
            run_id=run_id,
            parent_run_id=parent_run_id,
        )

        call_kwargs = mock_span_manager.start_span.call_args.kwargs
        assert (
            call_kwargs["attributes"][GenAI.GEN_AI_PROVIDER_NAME] == "openai"
        )

    def test_defaults_tool_name_to_retriever(self, handler, mock_span_manager):
        run_id = uuid4()
        handler.on_retriever_start(
            serialized={},
            query="test",
            run_id=run_id,
        )

        call_kwargs = mock_span_manager.start_span.call_args.kwargs
        assert call_kwargs["attributes"][GenAI.GEN_AI_TOOL_NAME] == "retriever"
        assert call_kwargs["name"] == f"{OP_EXECUTE_TOOL} retriever"

    def test_returns_early_when_no_span_manager(self):
        telemetry_handler = mock.MagicMock()
        h = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler,
            span_manager=None,
        )
        # Should not raise.
        h.on_retriever_start(
            serialized={"name": "retriever"},
            query="test",
            run_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# on_retriever_end
# ---------------------------------------------------------------------------


class TestOnRetrieverEnd:
    """on_retriever_end sets retrieval documents and ends span."""

    def test_sets_documents_with_content_when_enabled(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        span = _make_mock_span()
        record = _make_span_record(run_id, span=span)
        mock_span_manager.get_record.return_value = record

        docs = [
            mock.MagicMock(
                page_content="Document 1", metadata={"source": "a.txt"}
            ),
            mock.MagicMock(
                page_content="Document 2", metadata={"source": "b.txt"}
            ),
        ]

        formatted_json = json.dumps(
            [
                {
                    "page_content": "Document 1",
                    "metadata": {"source": "a.txt"},
                },
                {
                    "page_content": "Document 2",
                    "metadata": {"source": "b.txt"},
                },
            ]
        )

        with (
            mock.patch(
                "opentelemetry.instrumentation.langchain.callback_handler.should_record_retriever_content",
                return_value=True,
            ),
            mock.patch(
                "opentelemetry.instrumentation.langchain.callback_handler.format_documents",
                return_value=formatted_json,
            ) as mock_format,
        ):
            handler.on_retriever_end(
                documents=docs,
                run_id=run_id,
            )
            mock_format.assert_called_once_with(docs, record_content=True)

        span.set_attribute.assert_called_once_with(
            "gen_ai.retrieval.documents", formatted_json
        )

    def test_sets_documents_metadata_only_when_content_disabled(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        span = _make_mock_span()
        record = _make_span_record(run_id, span=span)
        mock_span_manager.get_record.return_value = record

        docs = [
            mock.MagicMock(
                page_content="Secret content",
                metadata={"source": "a.txt"},
            ),
        ]

        metadata_only_json = json.dumps([{"metadata": {"source": "a.txt"}}])

        with (
            mock.patch(
                "opentelemetry.instrumentation.langchain.callback_handler.should_record_retriever_content",
                return_value=False,
            ),
            mock.patch(
                "opentelemetry.instrumentation.langchain.callback_handler.format_documents",
                return_value=metadata_only_json,
            ) as mock_format,
        ):
            handler.on_retriever_end(
                documents=docs,
                run_id=run_id,
            )
            mock_format.assert_called_once_with(docs, record_content=False)

        span.set_attribute.assert_called_once_with(
            "gen_ai.retrieval.documents", metadata_only_json
        )

    def test_ends_span_with_ok_status(self, handler, mock_span_manager):
        run_id = uuid4()
        record = _make_span_record(run_id)
        mock_span_manager.get_record.return_value = record

        handler.on_retriever_end(
            documents=[],
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_called_once_with(
            run_id=str(run_id), status=StatusCode.OK
        )

    def test_returns_early_when_no_record(self, handler, mock_span_manager):
        run_id = uuid4()
        mock_span_manager.get_record.return_value = None

        handler.on_retriever_end(
            documents=[],
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_not_called()

    def test_returns_early_when_no_span_manager(self):
        telemetry_handler = mock.MagicMock()
        h = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler,
            span_manager=None,
        )
        # Should not raise.
        h.on_retriever_end(
            documents=[],
            run_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# on_retriever_error
# ---------------------------------------------------------------------------


class TestOnRetrieverError:
    """on_retriever_error ends the span with error status."""

    def test_ends_span_with_error(self, handler, mock_span_manager):
        run_id = uuid4()
        error = RuntimeError("retriever failed")

        handler.on_retriever_error(
            error=error,
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_called_once_with(
            run_id=str(run_id), error=error
        )

    def test_returns_early_when_no_span_manager(self):
        telemetry_handler = mock.MagicMock()
        h = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler,
            span_manager=None,
        )
        # Should not raise.
        h.on_retriever_error(
            error=RuntimeError("boom"),
            run_id=uuid4(),
        )
