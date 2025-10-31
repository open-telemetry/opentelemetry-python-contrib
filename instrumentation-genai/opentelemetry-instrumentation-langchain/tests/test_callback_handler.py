from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.attributes.azure_attributes import (
    AZURE_RESOURCE_PROVIDER_NAMESPACE,
)
from opentelemetry.semconv._incubating.attributes.openai_attributes import (
    OPENAI_RESPONSE_SERVICE_TIER,
    OPENAI_RESPONSE_SYSTEM_FINGERPRINT,
)


def _create_handler(capture_messages: bool = True):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    handler = OpenTelemetryLangChainCallbackHandler(
        tracer=provider.get_tracer(__name__),
        capture_messages=capture_messages,
    )
    return handler, exporter


def test_provider_and_server_metadata_extracted():
    handler, exporter = _create_handler()
    run_id = uuid4()

    handler.on_chat_model_start(
        serialized={"name": "CustomLLM"},
        messages=[],
        run_id=run_id,
        tags=None,
        parent_run_id=None,
        metadata={
            "ls_provider": "azure",
            "ls_model_name": "gpt-4o",
        },
        invocation_params={
            "params": {
                "model": "gpt-4o",
                "base_url": "https://example.openai.azure.com/openai/deployments/demo",
                "n": 2,
            }
        },
    )

    handler.span_manager.end_span(run_id)

    span = exporter.get_finished_spans()[0]
    assert span.name == "chat gpt-4o"
    assert span.attributes[GenAI.GEN_AI_PROVIDER_NAME] == "azure.ai.openai"
    assert (
        span.attributes[AZURE_RESOURCE_PROVIDER_NAMESPACE]
        == "Microsoft.CognitiveServices"
    )
    assert span.attributes["server.address"] == "example.openai.azure.com"
    assert span.attributes["server.port"] == 443
    assert span.attributes[GenAI.GEN_AI_REQUEST_CHOICE_COUNT] == 2


@dataclass
class _DummyLLMResult:
    generations: list[Any]
    llm_output: dict[str, Any]


@dataclass
class _DummyGeneration:
    message: Any
    generation_info: dict[str, Any] | None = None


@dataclass
class _FakeMessage:
    content: str
    type: str
    additional_kwargs: dict[str, Any] | None = None
    response_metadata: dict[str, Any] | None = None
    usage_metadata: dict[str, Any] | None = None
    id: str | None = None


def test_llm_end_sets_response_metadata():
    handler, exporter = _create_handler()
    run_id = uuid4()

    handler.on_chat_model_start(
        serialized={"name": "ChatOpenAI"},
        messages=[],
        run_id=run_id,
        tags=None,
        parent_run_id=None,
        metadata={"ls_model_name": "gpt-4"},
        invocation_params={"params": {"model": "gpt-4"}},
    )

    handler.on_llm_end(
        _DummyLLMResult(
            generations=[],
            llm_output={
                "model_name": "gpt-4-0125",
                "service_tier": "premium",
                "system_fingerprint": "fp-test",
                "id": "chatcmpl-test",
            },
        ),
        run_id=run_id,
        parent_run_id=None,
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes[GenAI.GEN_AI_RESPONSE_MODEL] == "gpt-4-0125"
    assert span.attributes[GenAI.GEN_AI_RESPONSE_ID] == "chatcmpl-test"
    assert span.attributes[OPENAI_RESPONSE_SERVICE_TIER] == "premium"
    assert span.attributes[OPENAI_RESPONSE_SYSTEM_FINGERPRINT] == "fp-test"


def test_choice_count_not_set_when_one():
    handler, exporter = _create_handler()
    run_id = uuid4()

    handler.on_chat_model_start(
        serialized={"name": "ChatOpenAI"},
        messages=[],
        run_id=run_id,
        tags=None,
        parent_run_id=None,
        metadata={"ls_model_name": "gpt-4"},
        invocation_params={
            "params": {
                "model": "gpt-4",
                "n": 1,
            }
        },
    )

    handler.span_manager.end_span(run_id)
    span = exporter.get_finished_spans()[0]
    assert GenAI.GEN_AI_REQUEST_CHOICE_COUNT not in span.attributes


def test_capture_messages_sets_attributes_by_default():
    handler, exporter = _create_handler()
    run_id = uuid4()

    handler.on_chat_model_start(
        serialized={"name": "ChatOpenAI"},
        messages=[
            [
                _FakeMessage(
                    content="hello",
                    type="human",
                    id="m1",
                )
            ]
        ],
        run_id=run_id,
        tags=None,
        parent_run_id=None,
        metadata={"ls_model_name": "gpt-4"},
        invocation_params={"params": {"model": "gpt-4"}},
    )

    handler.on_llm_end(
        _DummyLLMResult(
            generations=[
                [
                    _DummyGeneration(
                        message=_FakeMessage(
                            content="result",
                            type="ai",
                            id="m2",
                        )
                    )
                ]
            ],
            llm_output={},
        ),
        run_id=run_id,
        parent_run_id=None,
    )

    span = exporter.get_finished_spans()[0]
    input_payload = json.loads(span.attributes[GenAI.GEN_AI_INPUT_MESSAGES])
    output_payload = json.loads(span.attributes[GenAI.GEN_AI_OUTPUT_MESSAGES])
    assert input_payload[0]["content"] == "hello"
    assert output_payload[0]["content"] == "result"


def test_capture_messages_can_be_disabled():
    handler, exporter = _create_handler(capture_messages=False)
    run_id = uuid4()

    handler.on_chat_model_start(
        serialized={"name": "ChatOpenAI"},
        messages=[
            [
                _FakeMessage(
                    content="hello",
                    type="human",
                )
            ]
        ],
        run_id=run_id,
        tags=None,
        parent_run_id=None,
        metadata={"ls_model_name": "gpt-4"},
        invocation_params={"params": {"model": "gpt-4"}},
    )

    handler.on_llm_end(
        _DummyLLMResult(generations=[], llm_output={}),
        run_id=run_id,
        parent_run_id=None,
    )

    span = exporter.get_finished_spans()[0]
    assert GenAI.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert GenAI.GEN_AI_OUTPUT_MESSAGES not in span.attributes
