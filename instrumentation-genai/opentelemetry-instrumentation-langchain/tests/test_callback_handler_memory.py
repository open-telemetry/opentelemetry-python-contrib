from __future__ import annotations

from unittest import mock
from uuid import uuid4

from opentelemetry.instrumentation.langchain.callback_handler import (
    GEN_AI_MEMORY_QUERY,
    GEN_AI_MEMORY_SEARCH_RESULT_COUNT,
    GEN_AI_MEMORY_STORE_ID,
    GEN_AI_MEMORY_STORE_NAME,
    RETRIEVAL_OPERATION,
    SEARCH_MEMORY_OPERATION,
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.util.genai.types import ContentCapturingMode


def _build_handler():
    telemetry_handler = mock.Mock()

    def _start(invocation):
        span = mock.Mock()
        span.is_recording.return_value = True
        invocation.span = span
        return invocation

    telemetry_handler.start_llm.side_effect = _start
    telemetry_handler.stop_llm.side_effect = lambda invocation: invocation
    telemetry_handler.fail_llm.side_effect = (
        lambda invocation, error: invocation
    )
    return (
        OpenTelemetryLangChainCallbackHandler(telemetry_handler),
        telemetry_handler,
    )


def test_retriever_defaults_to_retrieval_without_memory_metadata(monkeypatch):
    """Retrievers without memory metadata should emit 'retrieval' operation."""
    handler, telemetry_handler = _build_handler()
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.is_experimental_mode",
        lambda: False,
    )

    run_id = uuid4()
    handler.on_retriever_start(
        serialized={"name": "PineconeRetriever"},
        query="what is RAG?",
        run_id=run_id,
        metadata={"ls_provider": "pinecone"},
    )

    invocation = handler._invocation_manager.get_invocation(run_id)
    assert invocation is not None
    assert invocation.operation_name == RETRIEVAL_OPERATION
    telemetry_handler.start_llm.assert_called_once()


def test_retriever_uses_search_memory_with_memory_metadata(monkeypatch):
    """Retrievers with memory_store_name in metadata should emit 'search_memory'."""
    handler, telemetry_handler = _build_handler()
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.is_experimental_mode",
        lambda: True,
    )
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.get_content_capturing_mode",
        lambda: ContentCapturingMode.SPAN_ONLY,
    )

    run_id = uuid4()
    handler.on_retriever_start(
        serialized={
            "name": "SessionMemoryRetriever",
            "id": ["langchain", "retriever", "session"],
        },
        query="user preferences",
        run_id=run_id,
        metadata={
            "ls_provider": "openai",
            "memory_store_name": "SessionMemoryRetriever",
            "memory_namespace": "user-123",
        },
    )

    invocation = handler._invocation_manager.get_invocation(run_id)
    assert invocation is not None
    assert invocation.operation_name == SEARCH_MEMORY_OPERATION
    assert (
        invocation.attributes[GEN_AI_MEMORY_STORE_NAME]
        == "SessionMemoryRetriever"
    )
    assert (
        invocation.attributes[GEN_AI_MEMORY_STORE_ID]
        == "langchain.retriever.session"
    )
    assert invocation.attributes[GEN_AI_MEMORY_QUERY] == "user preferences"
    telemetry_handler.start_llm.assert_called_once()


def test_on_retriever_end_sets_search_result_count(monkeypatch):
    handler, telemetry_handler = _build_handler()
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.is_experimental_mode",
        lambda: False,
    )

    run_id = uuid4()
    handler.on_retriever_start(
        serialized={"name": "MemoryRetriever"},
        query="q",
        run_id=run_id,
        metadata={"ls_provider": "openai"},
    )
    handler.on_retriever_end(documents=[object(), object()], run_id=run_id)

    telemetry_handler.stop_llm.assert_called_once()
    stop_invocation = telemetry_handler.stop_llm.call_args.kwargs["invocation"]
    assert stop_invocation.attributes[GEN_AI_MEMORY_SEARCH_RESULT_COUNT] == 2


def test_on_retriever_error_fails_invocation(monkeypatch):
    handler, telemetry_handler = _build_handler()
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.is_experimental_mode",
        lambda: False,
    )

    run_id = uuid4()
    handler.on_retriever_start(
        serialized={"name": "VectorRetriever"},
        query="q",
        run_id=run_id,
        metadata={"ls_provider": "openai"},
    )
    handler.on_retriever_error(RuntimeError("retrieval failed"), run_id=run_id)

    telemetry_handler.fail_llm.assert_called_once()
    fail_invocation = telemetry_handler.fail_llm.call_args.kwargs["invocation"]
    assert fail_invocation.operation_name == RETRIEVAL_OPERATION
