# ruff: noqa: E402
# pylint: disable=wrong-import-position,wrong-import-order,import-error,no-name-in-module,unexpected-keyword-arg,no-value-for-parameter,redefined-outer-name,too-many-lines

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

TESTS_ROOT = Path(__file__).resolve().parent
stub_path = TESTS_ROOT / "stubs"
if str(stub_path) not in sys.path:
    sys.path.insert(0, str(stub_path))

sys.modules.pop("agents", None)
sys.modules.pop("agents.tracing", None)

import agents.tracing as agents_tracing
import openai
from agents.tracing import (
    agent_span,
    function_span,
    generation_span,
    response_span,
    set_trace_processors,
    trace,
)
from openai.types.responses import (
    ResponseCodeInterpreterToolCall,
    ResponseComputerToolCall,
    ResponseCustomToolCall,
    ResponseFileSearchToolCall,
    ResponseFunctionToolCall,
    ResponseFunctionWebSearch,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningItem,
)
from openai.types.responses.response_code_interpreter_tool_call import (
    OutputLogs,
)
from openai.types.responses.response_computer_tool_call import (
    ActionClick,
)
from openai.types.responses.response_function_web_search import (
    ActionSearch as ActionWebSearch,
)
from openai.types.responses.response_output_item import (
    ImageGenerationCall,
    LocalShellCall,
    LocalShellCallAction,
    McpApprovalRequest,
    McpCall,
    McpListTools,
    McpListToolsTool,
)
from openai.types.responses.response_reasoning_item import (
    Content,
)

from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.instrumentation.openai_agents.span_processor import (
    ContentPayload,
    GenAISemanticProcessor,
)
from opentelemetry.sdk.trace import TracerProvider

try:
    from opentelemetry.sdk.trace.export import (  # type: ignore[attr-defined] pylint: disable=no-name-in-module
        InMemorySpanExporter,
        SimpleSpanProcessor,
    )
except ImportError:  # pragma: no cover - support older/newer SDK layouts
    from opentelemetry.sdk.trace.export import (
        SimpleSpanProcessor,
    )
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import SpanKind

GEN_AI_PROVIDER_NAME = GenAI.GEN_AI_PROVIDER_NAME
GEN_AI_INPUT_MESSAGES = getattr(
    GenAI, "GEN_AI_INPUT_MESSAGES", "gen_ai.input.messages"
)
GEN_AI_OUTPUT_MESSAGES = getattr(
    GenAI, "GEN_AI_OUTPUT_MESSAGES", "gen_ai.output.messages"
)


# dummy classes for some response types since concrete type is not available in older `openai` versions
class _ResponseCompactionItem(openai.BaseModel):
    pass


class _ActionShellCall(openai.BaseModel):
    pass


class _ResponseFunctionShellToolCall(openai.BaseModel):
    pass


class _OutputOutcomeExit(openai.BaseModel):
    pass


class _ShellToolCallOutput(openai.BaseModel):
    pass


class _ResponseFunctionShellToolCallOutput(openai.BaseModel):
    pass


class _OperationCreateFile(openai.BaseModel):
    pass


class _ResponseApplyPatchToolCall(openai.BaseModel):
    pass


class _ResponseApplyPatchToolCallOutput(openai.BaseModel):
    pass


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    def __init__(self) -> None:
        self.id = "resp-123"
        self.model = "gpt-4o-mini"
        self.usage = _Usage(42, 9)
        self.output = [
            # message type with output_text
            ResponseOutputMessage(
                id="msg-1",
                role="assistant",
                type="message",
                status="completed",
                content=[
                    ResponseOutputText(
                        type="output_text", text="Hello!", annotations=[]
                    )
                ],
            ),
            # message type with refusal
            ResponseOutputMessage(
                id="msg-2",
                role="assistant",
                type="message",
                status="completed",
                content=[
                    ResponseOutputRefusal(
                        type="refusal", refusal="I cannot do that"
                    )
                ],
            ),
            # reasoning
            ResponseReasoningItem(
                id="reason-1",
                type="reasoning",
                summary=[],
                content=[
                    Content(type="reasoning_text", text="Step 1: Think"),
                    Content(type="reasoning_text", text="Step 2: Act"),
                ],
            ),
            # compaction
            _ResponseCompactionItem(
                id="compact-1",
                type="compaction",
                encrypted_content="encrypted_data",
            ),
            # file_search_call
            ResponseFileSearchToolCall(
                type="file_search_call",
                id="fs-123",
                status="completed",
                queries=["search query"],
            ),
            # function_call
            ResponseFunctionToolCall(
                name="get_weather",
                id="fc-123",
                type="function_call",
                call_id="call-fc-123",
                arguments='{"city": "Paris"}',
            ),
            # web_search_call
            ResponseFunctionWebSearch(
                id="ws-123",
                type="web_search_call",
                status="completed",
                action=ActionWebSearch(type="search", query="test"),
            ),
            # computer_call
            ResponseComputerToolCall(
                id="cc-123",
                type="computer_call",
                call_id="call-cc-123",
                status="completed",
                pending_safety_checks=[],
                action=ActionClick(type="click", x=100, y=200, button="left"),
            ),
            # image_generation_call
            ImageGenerationCall(
                id="ig-123",
                status="completed",
                type="image_generation_call",
                result="image_url",
            ),
            # code_interpreter_call
            ResponseCodeInterpreterToolCall(
                id="ci-123",
                type="code_interpreter_call",
                status="completed",
                container_id="cont-123",
                code="print('hello')",
                outputs=[OutputLogs(type="logs", logs="hello")],
            ),
            # local_shell_call
            LocalShellCall(
                id="ls-123",
                call_id="call-ls-123",
                type="local_shell_call",
                status="completed",
                action=LocalShellCallAction(
                    type="exec",
                    timeout_ms=5000,
                    command=["ls", "-la"],
                    env={"PATH": "/usr/bin"},
                    user="root",
                    working_directory="/tmp",
                ),
            ),
            # shell_call
            _ResponseFunctionShellToolCall(
                id="sh-123",
                type="shell_call",
                status="completed",
                call_id="call-123",
                action=_ActionShellCall(
                    commands=["echo hello"],
                    max_output_length=1000,
                    timeout_ms=5000,
                ),
            ),
            # shell_call_output
            _ResponseFunctionShellToolCallOutput(
                id="sho-123",
                type="shell_call_output",
                status="completed",
                call_id="call-123",
                output=[
                    _ShellToolCallOutput(
                        stdout="shell output",
                        stderr="",
                        outcome=_OutputOutcomeExit(type="exit", exit_code=0),
                    )
                ],
            ),
            # apply_patch_call
            _ResponseApplyPatchToolCall(
                id="ap-123",
                type="apply_patch_call",
                status="completed",
                created_by="agent",
                call_id="call-123",
                operation=_OperationCreateFile(
                    type="create_file",
                    diff="content",
                    path="/tmp/test.txt",
                ),
            ),
            # apply_patch_call_output
            _ResponseApplyPatchToolCallOutput(
                id="apo-123",
                type="apply_patch_call_output",
                created_by="agent",
                call_id="call-123",
                status="completed",
                output="Applied successfully",
            ),
            # mcp_call with output
            McpCall(
                id="mcp-123",
                server_label="server1",
                name="tool_name",
                type="mcp_call",
                arguments='{"key": "value"}',
                output="result",
                error=None,
                status="completed",
            ),
            # mcp_call with error
            McpCall(
                id="mcp-124",
                server_label="server1",
                name="tool_name",
                type="mcp_call",
                arguments='{"key": "value"}',
                output=None,
                error="Some error",
                status="failed",
            ),
            # mcp_call without output (no response part)
            McpCall(
                id="mcp-125",
                server_label="server2",
                name="another_tool",
                type="mcp_call",
                arguments='{"key": "value2"}',
                output=None,
                error=None,
            ),
            # mcp_list_tools with tools
            McpListTools(
                id="mcpl-123",
                server_label="server1",
                type="mcp_list_tools",
                tools=[
                    McpListToolsTool(name="tool1", input_schema={}),
                    McpListToolsTool(name="tool2", input_schema={}),
                ],
                error=None,
            ),
            # mcp_list_tools without tools (no response part)
            McpListTools(
                id="mcpl-124",
                server_label="server2",
                type="mcp_list_tools",
                tools=[],
                error=None,
            ),
            # mcp_approval_request
            McpApprovalRequest(
                id="mcpa-123",
                server_label="server1",
                name="dangerous_tool",
                type="mcp_approval_request",
                arguments='{"action": "delete"}',
            ),
            # custom_tool_call
            ResponseCustomToolCall(
                name="custom_tool",
                id="ct-123",
                type="custom_tool_call",
                call_id="call-ct-123",
                input="input",
            ),
            # fallback with content string
            {
                "type": "unknown_type",
                "content": "fallback content",
            },
            # fallback to stringified (no content attribute)
            {
                "type": "another_unknown",
                "data": "some data",
            },
        ]


def _instrument_with_provider(**instrument_kwargs):
    set_trace_processors([])
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    instrumentor = OpenAIAgentsInstrumentor()
    instrumentor.instrument(tracer_provider=provider, **instrument_kwargs)

    return instrumentor, exporter


def test_generation_span_creates_client_span():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"role": "user", "content": "hi"}],
                output=[{"role": "assistant", "content": "hello"}],
                model="gpt-4o-mini",
                model_config={
                    "temperature": 0.2,
                    "base_url": "https://api.openai.com",
                },
                usage={"input_tokens": 12, "output_tokens": 3},
            ):
                pass

        spans = exporter.get_finished_spans()
        client_span = next(
            span for span in spans if span.kind is SpanKind.CLIENT
        )

        assert client_span.attributes[GEN_AI_PROVIDER_NAME] == "openai"
        assert client_span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "chat"
        assert (
            client_span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
        )
        assert client_span.name == "chat gpt-4o-mini"
        assert client_span.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 12
        assert client_span.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 3
        assert (
            client_span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.openai.com"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_generation_span_without_roles_uses_text_completion():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"content": "tell me a joke"}],
                model="gpt-4o-mini",
                model_config={"temperature": 0.7},
            ):
                pass

        spans = exporter.get_finished_spans()
        completion_span = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value
        )

        assert completion_span.kind is SpanKind.CLIENT
        assert completion_span.name == "text_completion gpt-4o-mini"
        assert (
            completion_span.attributes[GenAI.GEN_AI_REQUEST_MODEL]
            == "gpt-4o-mini"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_function_span_records_tool_attributes():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with function_span(
                name="fetch_weather", input='{"city": "Paris"}'
            ):
                pass

        spans = exporter.get_finished_spans()
        tool_span = next(
            span for span in spans if span.kind is SpanKind.INTERNAL
        )

        assert (
            tool_span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"
        )
        assert tool_span.attributes[GenAI.GEN_AI_TOOL_NAME] == "fetch_weather"
        assert tool_span.attributes[GenAI.GEN_AI_TOOL_TYPE] == "function"
        assert tool_span.attributes[GEN_AI_PROVIDER_NAME] == "openai"
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_agent_create_span_records_attributes():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with agent_span(
                operation="create",
                name="support_bot",
                description="Answers support questions",
                agent_id="agt_123",
                model="gpt-4o-mini",
            ):
                pass

        spans = exporter.get_finished_spans()
        create_span = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.CREATE_AGENT.value
        )

        assert create_span.kind is SpanKind.CLIENT
        assert create_span.name == "create_agent support_bot"
        assert create_span.attributes[GEN_AI_PROVIDER_NAME] == "openai"
        assert create_span.attributes[GenAI.GEN_AI_AGENT_NAME] == "support_bot"
        assert (
            create_span.attributes[GenAI.GEN_AI_AGENT_DESCRIPTION]
            == "Answers support questions"
        )
        assert create_span.attributes[GenAI.GEN_AI_AGENT_ID] == "agt_123"
        assert (
            create_span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def _placeholder_message() -> dict[str, Any]:
    return {
        "role": "user",
        "parts": [{"type": "text", "content": "readacted"}],
    }


def test_normalize_messages_skips_empty_when_sensitive_enabled():
    processor = GenAISemanticProcessor(metrics_enabled=False)
    normalized = processor._normalize_messages_to_role_parts(
        [{"role": "user", "content": None}]
    )
    assert not normalized


def test_normalize_messages_emits_placeholder_when_sensitive_disabled():
    processor = GenAISemanticProcessor(
        include_sensitive_data=False, metrics_enabled=False
    )
    normalized = processor._normalize_messages_to_role_parts(
        [{"role": "user", "content": None}]
    )
    assert normalized == [_placeholder_message()]


def test_agent_content_aggregation_skips_duplicate_snapshots():
    processor = GenAISemanticProcessor(metrics_enabled=False)
    agent_id = "agent-span"
    processor._agent_content[agent_id] = {
        "input_messages": [],
        "output_messages": [],
        "system_instructions": [],
    }

    payload = ContentPayload(
        input_messages=[
            {"role": "user", "parts": [{"type": "text", "content": "hello"}]},
            {
                "role": "user",
                "parts": [{"type": "text", "content": "readacted"}],
            },
        ]
    )

    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-1", parent_id=agent_id, span_data=None),
        payload,
    )
    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-2", parent_id=agent_id, span_data=None),
        payload,
    )

    aggregated = processor._agent_content[agent_id]["input_messages"]
    assert aggregated == [
        {"role": "user", "parts": [{"type": "text", "content": "hello"}]}
    ]
    # ensure data copied rather than reused to prevent accidental mutation
    assert aggregated is not payload.input_messages


def test_agent_content_aggregation_filters_placeholder_append_when_sensitive():
    processor = GenAISemanticProcessor(metrics_enabled=False)
    agent_id = "agent-span"
    processor._agent_content[agent_id] = {
        "input_messages": [],
        "output_messages": [],
        "system_instructions": [],
    }

    initial_payload = ContentPayload(
        input_messages=[
            {"role": "user", "parts": [{"type": "text", "content": "hello"}]}
        ]
    )
    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-1", parent_id=agent_id, span_data=None),
        initial_payload,
    )

    placeholder_payload = ContentPayload(
        input_messages=[_placeholder_message()]
    )
    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-2", parent_id=agent_id, span_data=None),
        placeholder_payload,
    )

    aggregated = processor._agent_content[agent_id]["input_messages"]
    assert aggregated == [
        {"role": "user", "parts": [{"type": "text", "content": "hello"}]}
    ]


def test_agent_content_aggregation_retains_placeholder_when_sensitive_disabled():
    processor = GenAISemanticProcessor(
        include_sensitive_data=False, metrics_enabled=False
    )
    agent_id = "agent-span"
    processor._agent_content[agent_id] = {
        "input_messages": [],
        "output_messages": [],
        "system_instructions": [],
    }

    placeholder_payload = ContentPayload(
        input_messages=[_placeholder_message()]
    )
    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-1", parent_id=agent_id, span_data=None),
        placeholder_payload,
    )

    aggregated = processor._agent_content[agent_id]["input_messages"]
    assert aggregated == [_placeholder_message()]


def test_agent_content_aggregation_appends_new_messages_once():
    processor = GenAISemanticProcessor(metrics_enabled=False)
    agent_id = "agent-span"
    processor._agent_content[agent_id] = {
        "input_messages": [],
        "output_messages": [],
        "system_instructions": [],
    }

    initial_payload = ContentPayload(
        input_messages=[
            {"role": "user", "parts": [{"type": "text", "content": "hello"}]}
        ]
    )
    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-1", parent_id=agent_id, span_data=None),
        initial_payload,
    )

    extended_messages = [
        {"role": "user", "parts": [{"type": "text", "content": "hello"}]},
        {
            "role": "assistant",
            "parts": [{"type": "text", "content": "hi there"}],
        },
    ]
    extended_payload = ContentPayload(input_messages=extended_messages)
    processor._update_agent_aggregate(
        SimpleNamespace(span_id="child-2", parent_id=agent_id, span_data=None),
        extended_payload,
    )

    aggregated = processor._agent_content[agent_id]["input_messages"]
    assert aggregated == extended_messages
    assert extended_payload.input_messages == extended_messages


def test_agent_span_collects_child_messages():
    instrumentor, exporter = _instrument_with_provider()

    try:
        provider = agents_tracing.get_trace_provider()

        with trace("workflow") as workflow:
            agent_span_obj = provider.create_span(
                agents_tracing.AgentSpanData(name="helper"),
                parent=workflow,
            )
            agent_span_obj.start()

            generation = agents_tracing.GenerationSpanData(
                input=[{"role": "user", "content": "hi"}],
                output=[{"type": "text", "content": "hello"}],
                model="gpt-4o-mini",
            )
            gen_span = provider.create_span(generation, parent=agent_span_obj)
            gen_span.start()
            gen_span.finish()

            agent_span_obj.finish()

        spans = exporter.get_finished_spans()
        agent_span = next(
            span
            for span in spans
            if span.attributes.get(GenAI.GEN_AI_OPERATION_NAME)
            == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        )

        prompt = json.loads(agent_span.attributes[GEN_AI_INPUT_MESSAGES])
        completion = json.loads(agent_span.attributes[GEN_AI_OUTPUT_MESSAGES])

        assert prompt == [
            {
                "role": "user",
                "parts": [{"type": "text", "content": "hi"}],
            }
        ]
        assert completion == [
            {
                "role": "assistant",
                "parts": [{"type": "text", "content": "hello"}],
            }
        ]

        assert not agent_span.events
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_agent_name_override_applied_to_agent_spans():
    instrumentor, exporter = _instrument_with_provider(
        agent_name="Travel Concierge"
    )

    try:
        with trace("workflow"):
            with agent_span(operation="invoke", name="support_bot"):
                pass

        spans = exporter.get_finished_spans()
        agent_span_record = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        )

        assert agent_span_record.kind is SpanKind.CLIENT
        assert agent_span_record.name == "invoke_agent Travel Concierge"
        assert (
            agent_span_record.attributes[GenAI.GEN_AI_AGENT_NAME]
            == "Travel Concierge"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_capture_mode_can_be_disabled():
    instrumentor, exporter = _instrument_with_provider(
        capture_message_content="no_content"
    )

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"role": "user", "content": "hi"}],
                output=[{"role": "assistant", "content": "hello"}],
                model="gpt-4o-mini",
            ):
                pass

        spans = exporter.get_finished_spans()
        client_span = next(
            span for span in spans if span.kind is SpanKind.CLIENT
        )

        assert GEN_AI_INPUT_MESSAGES not in client_span.attributes
        assert GEN_AI_OUTPUT_MESSAGES not in client_span.attributes
        for event in client_span.events:
            assert GEN_AI_INPUT_MESSAGES not in event.attributes
            assert GEN_AI_OUTPUT_MESSAGES not in event.attributes
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_response_span_records_redacted_response_attributes():
    instrumentor, exporter = _instrument_with_provider(
        capture_message_content=False,
    )

    try:
        with trace("workflow"):
            with response_span(response=_Response()):
                pass

        spans = exporter.get_finished_spans()
        response = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.CHAT.value
        )

        assert response.kind is SpanKind.CLIENT
        assert response.name == "chat gpt-4o-mini"
        assert response.attributes[GEN_AI_PROVIDER_NAME] == "openai"
        assert response.attributes[GenAI.GEN_AI_RESPONSE_ID] == "resp-123"
        assert (
            response.attributes[GenAI.GEN_AI_RESPONSE_MODEL] == "gpt-4o-mini"
        )
        assert response.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 42
        assert response.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 9

        # Check output messages are redacted
        assert GEN_AI_OUTPUT_MESSAGES not in response.attributes
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_response_span_records_response_attributes():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with response_span(response=_Response()):
                pass

        spans = exporter.get_finished_spans()
        response = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.CHAT.value
        )

        assert response.kind is SpanKind.CLIENT
        assert response.name == "chat gpt-4o-mini"
        assert response.attributes[GEN_AI_PROVIDER_NAME] == "openai"
        assert response.attributes[GenAI.GEN_AI_RESPONSE_ID] == "resp-123"
        assert (
            response.attributes[GenAI.GEN_AI_RESPONSE_MODEL] == "gpt-4o-mini"
        )
        assert response.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 42
        assert response.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 9

        # Check output messages are properly normalized
        output_messages = json.loads(
            response.attributes[GEN_AI_OUTPUT_MESSAGES]
        )
        assert len(output_messages) == 1
        assert output_messages[0]["role"] == "assistant"
        parts = output_messages[0]["parts"]
        tool_calls_by_id = {
            part["id"]: {k: v for k, v in part.items() if k != "id"}
            for part in parts
            if part.get("type") == "tool_call"
        }
        tool_call_responses_by_id = {
            part["id"]: {k: v for k, v in part.items() if k != "id"}
            for part in parts
            if part.get("type") == "tool_call_response"
        }

        assert parts[0] == {
            "type": "text",
            "content": "Hello!",
            "annotations": [],
        }

        assert parts[1] == {
            "type": "refusal",
            "content": "I cannot do that",
        }

        assert parts[2] == {
            "type": "reasoning",
            "content": "Step 1: Think\nStep 2: Act",
        }

        assert parts[3] == {
            "type": "compaction",
            "content": "encrypted_data",
        }

        assert tool_calls_by_id["fs-123"] == {
            "type": "tool_call",
            "name": "file_search",
            "arguments": {"queries": ["search query"]},
        }

        assert tool_calls_by_id["fc-123"] == {
            "type": "tool_call",
            "name": "get_weather",
            "arguments": {"city": "Paris"},
        }

        assert tool_calls_by_id["ws-123"] == {
            "type": "tool_call",
            "name": "web_search",
            "arguments": {"action": {"type": "search", "query": "test"}},
        }

        assert tool_calls_by_id["cc-123"] == {
            "type": "tool_call",
            "name": "computer",
            "arguments": {
                "action": {
                    "type": "click",
                    "x": 100,
                    "y": 200,
                    "button": "left",
                }
            },
        }

        assert tool_calls_by_id["ci-123"] == {
            "type": "tool_call",
            "name": "code_interpreter",
            "arguments": {
                "code": "print('hello')",
                "container_id": "cont-123",
            },
        }

        assert tool_call_responses_by_id["ci-123"] == {
            "type": "tool_call_response",
            "name": "code_interpreter",
            "response": {
                "status": "completed",
                "outputs": [{"type": "logs", "logs": "hello"}],
            },
        }

        assert tool_calls_by_id["ls-123"] == {
            "type": "tool_call",
            "name": "local_shell",
            "arguments": {
                "command": ["ls", "-la"],
                "env": {"PATH": "/usr/bin"},
                "type": "exec",
                "user": "root",
                "working_directory": "/tmp",
                "timeout_ms": 5000,
            },
        }

        assert tool_calls_by_id["sh-123"] == {
            "type": "tool_call",
            "name": "shell",
            "arguments": {
                "call_id": "call-123",
                "commands": ["echo hello"],
                "created_by": None,
                "environment": None,
                "max_output_length": 1000,
                "timeout_ms": 5000,
            },
        }

        assert tool_calls_by_id["ap-123"] == {
            "type": "tool_call",
            "name": "apply_patch",
            "arguments": {
                "call_id": "call-123",
                "operation": {
                    "type": "create_file",
                    "diff": "content",
                    "path": "/tmp/test.txt",
                },
                "created_by": "agent",
            },
        }

        assert tool_call_responses_by_id["apo-123"] == {
            "type": "tool_call_response",
            "name": "apply_patch",
            "response": {
                "call_id": "call-123",
                "created_by": "agent",
                "status": "completed",
                "output": "Applied successfully",
            },
        }

        assert tool_calls_by_id["mcp-123"] == {
            "type": "tool_call",
            "name": "mcp_call",
            "arguments": {
                "server": "server1",
                "tool_name": "tool_name",
                "tool_args": {"key": "value"},
            },
        }

        assert tool_call_responses_by_id["mcp-123"] == {
            "type": "tool_call_response",
            "name": "mcp_call",
            "response": {
                "output": "result",
                "error": None,
                "status": "completed",
            },
        }

        assert tool_call_responses_by_id["mcp-124"] == {
            "type": "tool_call_response",
            "name": "mcp_call",
            "response": {
                "output": None,
                "error": "Some error",
                "status": "failed",
            },
        }

        assert tool_calls_by_id["mcp-125"] == {
            "type": "tool_call",
            "name": "mcp_call",
            "arguments": {
                "server": "server2",
                "tool_name": "another_tool",
                "tool_args": {"key": "value2"},
            },
        }

        assert tool_calls_by_id["mcpl-123"] == {
            "type": "tool_call",
            "name": "mcp_list_tools",
            "arguments": {
                "server": "server1",
            },
        }

        assert tool_call_responses_by_id["mcpl-123"] == {
            "type": "tool_call_response",
            "name": "mcp_list_tools",
            "response": {
                "error": None,
                "tools": [
                    {"name": "tool1", "input_schema": {}},
                    {"name": "tool2", "input_schema": {}},
                ],
            },
        }

        assert tool_calls_by_id["mcpl-124"] == {
            "type": "tool_call",
            "name": "mcp_list_tools",
            "arguments": {
                "server": "server2",
            },
        }

        assert tool_calls_by_id["mcpa-123"] == {
            "type": "tool_call",
            "name": "mcp_approval_request",
            "arguments": {
                "server": "server1",
                "tool_name": "dangerous_tool",
                "tool_args": {"action": "delete"},
            },
        }

        assert tool_calls_by_id["ct-123"] == {
            "type": "tool_call",
            "name": "custom_tool",
            "arguments": "input",
        }

    finally:
        instrumentor.uninstrument()
        exporter.clear()
