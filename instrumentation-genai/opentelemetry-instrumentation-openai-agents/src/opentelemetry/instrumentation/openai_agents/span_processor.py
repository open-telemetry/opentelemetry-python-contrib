from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from time import time_ns
from typing import Any
from urllib.parse import urlparse

try:  # pragma: no cover - used when OpenAI Agents is available
    from agents.tracing.processor_interface import TracingProcessor
    from agents.tracing.spans import Span as AgentsSpan
    from agents.tracing.traces import Trace as AgentsTrace
except ImportError:  # pragma: no cover - fallback for tests

    class TracingProcessor:  # type: ignore[misc]
        pass

    AgentsSpan = Any  # type: ignore[assignment]
    AgentsTrace = Any  # type: ignore[assignment]
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode

SPAN_TYPE_GENERATION = "generation"
SPAN_TYPE_RESPONSE = "response"
SPAN_TYPE_AGENT = "agent"
SPAN_TYPE_AGENT_CREATION = "agent_creation"
SPAN_TYPE_FUNCTION = "function"
SPAN_TYPE_SPEECH = "speech"
SPAN_TYPE_TRANSCRIPTION = "transcription"
SPAN_TYPE_SPEECH_GROUP = "speech_group"
SPAN_TYPE_GUARDRAIL = "guardrail"
SPAN_TYPE_HANDOFF = "handoff"
SPAN_TYPE_MCP_TOOLS = "mcp_tools"

_CLIENT_SPAN_TYPES = frozenset(
    {
        SPAN_TYPE_GENERATION,
        SPAN_TYPE_RESPONSE,
        SPAN_TYPE_SPEECH,
        SPAN_TYPE_TRANSCRIPTION,
        SPAN_TYPE_AGENT,
        SPAN_TYPE_AGENT_CREATION,
    }
)

_GEN_AI_PROVIDER_NAME = GenAI.GEN_AI_PROVIDER_NAME


def _parse_iso8601(timestamp: str | None) -> int | None:
    """Return nanosecond timestamp for ISO8601 string."""

    if not timestamp:
        return None

    try:
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return None

    return int(dt.timestamp() * 1_000_000_000)


def _extract_server_attributes(
    config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not config:
        return {}

    base_url = config.get("base_url")
    if not isinstance(base_url, str):
        return {}

    try:
        parsed = urlparse(base_url)
    except ValueError:
        return {}

    attributes: dict[str, Any] = {}
    if parsed.hostname:
        attributes[ServerAttributes.SERVER_ADDRESS] = parsed.hostname
    if parsed.port:
        attributes[ServerAttributes.SERVER_PORT] = parsed.port

    return attributes


def _looks_like_chat(messages: Sequence[Mapping[str, Any]] | None) -> bool:
    if not messages:
        return False
    for message in messages:
        if isinstance(message, Mapping) and message.get("role"):
            return True
    return False


def _collect_finish_reasons(choices: Sequence[Any] | None) -> list[str]:
    reasons: list[str] = []
    if not choices:
        return reasons

    for choice in choices:
        if isinstance(choice, Mapping):
            reason = choice.get("finish_reason") or choice.get("stop_reason")
            if reason:
                reasons.append(str(reason))
            continue

        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason:
            reasons.append(str(finish_reason))

    return reasons


def _clean_stop_sequences(value: Any) -> Sequence[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        cleaned: list[str] = []
        for item in value:
            if item is None:
                continue
            cleaned.append(str(item))
        return cleaned if cleaned else None
    return None


@dataclass
class _SpanContext:
    span: Span
    kind: SpanKind


class _OpenAIAgentsSpanProcessor(TracingProcessor):
    """Convert OpenAI Agents traces into OpenTelemetry spans."""

    def __init__(
        self,
        tracer: Tracer,
        system: str,
        agent_name_override: str | None = None,
    ) -> None:
        self._tracer = tracer
        self._system = system
        self._agent_name_override = (
            agent_name_override.strip()
            if isinstance(agent_name_override, str)
            and agent_name_override.strip()
            else None
        )
        self._root_spans: dict[str, Span] = {}
        self._spans: dict[str, _SpanContext] = {}
        self._lock = RLock()

    def _operation_name(self, span_data: Any) -> str:
        span_type = getattr(span_data, "type", None)
        explicit_operation = getattr(span_data, "operation", None)
        normalized_operation = (
            explicit_operation.strip().lower()
            if isinstance(explicit_operation, str)
            else None
        )
        if span_type == SPAN_TYPE_GENERATION:
            if _looks_like_chat(getattr(span_data, "input", None)):
                return GenAI.GenAiOperationNameValues.CHAT.value
            return GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value
        if span_type == SPAN_TYPE_AGENT:
            if normalized_operation in {"create", "create_agent"}:
                return GenAI.GenAiOperationNameValues.CREATE_AGENT.value
            if normalized_operation in {"invoke", "invoke_agent"}:
                return GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
            return GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        if span_type == SPAN_TYPE_AGENT_CREATION:
            return GenAI.GenAiOperationNameValues.CREATE_AGENT.value
        if span_type == SPAN_TYPE_FUNCTION:
            return GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
        if span_type == SPAN_TYPE_RESPONSE:
            return GenAI.GenAiOperationNameValues.CHAT.value
        return span_type or "operation"

    def _span_kind(self, span_data: Any) -> SpanKind:
        span_type = getattr(span_data, "type", None)
        if span_type in _CLIENT_SPAN_TYPES:
            return SpanKind.CLIENT
        # Tool invocations (e.g. span type "function") execute inside the agent
        # runtime, so there is no remote peer to model; we keep them INTERNAL.
        return SpanKind.INTERNAL

    def _span_name(self, operation: str, attributes: Mapping[str, Any]) -> str:
        model = attributes.get(GenAI.GEN_AI_REQUEST_MODEL) or attributes.get(
            GenAI.GEN_AI_RESPONSE_MODEL
        )
        agent_name = attributes.get(GenAI.GEN_AI_AGENT_NAME)
        tool_name = attributes.get(GenAI.GEN_AI_TOOL_NAME)

        if operation in (
            GenAI.GenAiOperationNameValues.CHAT.value,
            GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value,
            GenAI.GenAiOperationNameValues.GENERATE_CONTENT.value,
            GenAI.GenAiOperationNameValues.EMBEDDINGS.value,
        ):
            return f"{operation} {model}" if model else operation
        if operation == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value:
            return f"{operation} {agent_name}" if agent_name else operation
        if operation == GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value:
            return f"{operation} {tool_name}" if tool_name else operation
        if operation == GenAI.GenAiOperationNameValues.CREATE_AGENT.value:
            return f"{operation} {agent_name}" if agent_name else operation
        return operation

    def _base_attributes(self) -> dict[str, Any]:
        return {_GEN_AI_PROVIDER_NAME: self._system}

    def _attributes_from_generation(self, span_data: Any) -> dict[str, Any]:
        attributes = self._base_attributes()
        attributes[GenAI.GEN_AI_OPERATION_NAME] = self._operation_name(
            span_data
        )

        model = getattr(span_data, "model", None)
        if model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = model

        attributes.update(
            _extract_server_attributes(
                getattr(span_data, "model_config", None)
            )
        )

        usage = getattr(span_data, "usage", None)
        if isinstance(usage, Mapping):
            input_tokens = usage.get("prompt_tokens") or usage.get(
                "input_tokens"
            )
            if input_tokens is not None:
                attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] = input_tokens
            output_tokens = usage.get("completion_tokens") or usage.get(
                "output_tokens"
            )
            if output_tokens is not None:
                attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] = output_tokens

        model_config = getattr(span_data, "model_config", None)
        if isinstance(model_config, Mapping):
            mapping = {
                "temperature": GenAI.GEN_AI_REQUEST_TEMPERATURE,
                "top_p": GenAI.GEN_AI_REQUEST_TOP_P,
                "top_k": GenAI.GEN_AI_REQUEST_TOP_K,
                "frequency_penalty": GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY,
                "presence_penalty": GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY,
                "seed": GenAI.GEN_AI_REQUEST_SEED,
                "n": GenAI.GEN_AI_REQUEST_CHOICE_COUNT,
            }
            for key, attr in mapping.items():
                value = model_config.get(key)
                if value is not None:
                    attributes[attr] = value

            for max_key in ("max_tokens", "max_completion_tokens"):
                value = model_config.get(max_key)
                if value is not None:
                    attributes[GenAI.GEN_AI_REQUEST_MAX_TOKENS] = value
                    break

            stop_sequences = _clean_stop_sequences(model_config.get("stop"))
            if stop_sequences:
                attributes[GenAI.GEN_AI_REQUEST_STOP_SEQUENCES] = (
                    stop_sequences
                )

        attributes[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] = (
            _collect_finish_reasons(getattr(span_data, "output", None))
        )

        return attributes

    def _attributes_from_response(self, span_data: Any) -> dict[str, Any]:
        attributes = self._base_attributes()
        attributes[GenAI.GEN_AI_OPERATION_NAME] = self._operation_name(
            span_data
        )

        response = getattr(span_data, "response", None)
        if response is None:
            return attributes

        response_id = getattr(response, "id", None)
        if response_id is not None:
            attributes[GenAI.GEN_AI_RESPONSE_ID] = response_id

        response_model = getattr(response, "model", None)
        if response_model:
            attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model

        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "input_tokens", None) or getattr(
                usage, "prompt_tokens", None
            )
            if input_tokens is not None:
                attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] = input_tokens
            output_tokens = getattr(usage, "output_tokens", None) or getattr(
                usage, "completion_tokens", None
            )
            if output_tokens is not None:
                attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] = output_tokens

        output = getattr(response, "output", None)
        if output:
            attributes[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] = (
                _collect_finish_reasons(output)
            )

        return attributes

    def _attributes_from_agent(self, span_data: Any) -> dict[str, Any]:
        attributes = self._base_attributes()
        attributes[GenAI.GEN_AI_OPERATION_NAME] = (
            GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        )

        name = self._agent_name_override or getattr(span_data, "name", None)
        if name:
            attributes[GenAI.GEN_AI_AGENT_NAME] = name
        output_type = getattr(span_data, "output_type", None)
        if output_type:
            attributes[GenAI.GEN_AI_OUTPUT_TYPE] = output_type

        return attributes

    def _attributes_from_agent_creation(
        self, span_data: Any
    ) -> dict[str, Any]:
        attributes = self._base_attributes()
        attributes[GenAI.GEN_AI_OPERATION_NAME] = (
            GenAI.GenAiOperationNameValues.CREATE_AGENT.value
        )

        name = self._agent_name_override or getattr(span_data, "name", None)
        if name:
            attributes[GenAI.GEN_AI_AGENT_NAME] = name
        description = getattr(span_data, "description", None)
        if description:
            attributes[GenAI.GEN_AI_AGENT_DESCRIPTION] = description
        agent_id = getattr(span_data, "agent_id", None) or getattr(
            span_data, "id", None
        )
        if agent_id:
            attributes[GenAI.GEN_AI_AGENT_ID] = agent_id
        model = getattr(span_data, "model", None)
        if model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = model

        return attributes

    def _attributes_from_function(self, span_data: Any) -> dict[str, Any]:
        attributes = self._base_attributes()
        attributes[GenAI.GEN_AI_OPERATION_NAME] = (
            GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
        )

        name = getattr(span_data, "name", None)
        if name:
            attributes[GenAI.GEN_AI_TOOL_NAME] = name
        attributes[GenAI.GEN_AI_TOOL_TYPE] = "function"

        return attributes

    def _attributes_from_generic(self, span_data: Any) -> dict[str, Any]:
        attributes = self._base_attributes()
        attributes[GenAI.GEN_AI_OPERATION_NAME] = self._operation_name(
            span_data
        )
        return attributes

    def _attributes_for_span(self, span_data: Any) -> dict[str, Any]:
        span_type = getattr(span_data, "type", None)
        if span_type == SPAN_TYPE_GENERATION:
            return self._attributes_from_generation(span_data)
        if span_type == SPAN_TYPE_RESPONSE:
            return self._attributes_from_response(span_data)
        if span_type == SPAN_TYPE_AGENT:
            operation = getattr(span_data, "operation", None)
            if isinstance(operation, str) and operation.strip().lower() in {
                "create",
                "create_agent",
            }:
                return self._attributes_from_agent_creation(span_data)
            return self._attributes_from_agent(span_data)
        if span_type == SPAN_TYPE_AGENT_CREATION:
            return self._attributes_from_agent_creation(span_data)
        if span_type == SPAN_TYPE_FUNCTION:
            return self._attributes_from_function(span_data)
        if span_type in {
            SPAN_TYPE_GUARDRAIL,
            SPAN_TYPE_HANDOFF,
            SPAN_TYPE_SPEECH_GROUP,
            SPAN_TYPE_SPEECH,
            SPAN_TYPE_TRANSCRIPTION,
            SPAN_TYPE_MCP_TOOLS,
        }:
            return self._attributes_from_generic(span_data)
        return self._base_attributes()

    def on_trace_start(self, trace: AgentsTrace) -> None:
        # TODO: Confirm with the GenAI SIG whether emitting a SERVER workflow span
        # is the desired long-term shape once the semantic conventions define
        # top-level agent spans.
        attributes = self._base_attributes()
        start_time = (
            _parse_iso8601(getattr(trace, "started_at", None)) or time_ns()
        )

        with self._lock:
            span = self._tracer.start_span(
                name=trace.name,
                kind=SpanKind.SERVER,
                attributes=attributes,
                start_time=start_time,
            )
            self._root_spans[trace.trace_id] = span

    def on_trace_end(self, trace: AgentsTrace) -> None:
        end_time = _parse_iso8601(getattr(trace, "ended_at", None))

        with self._lock:
            span = self._root_spans.pop(trace.trace_id, None)

        if span:
            span.end(end_time=end_time)

    def on_span_start(self, span: AgentsSpan[Any]) -> None:
        span_data = span.span_data
        start_time = _parse_iso8601(span.started_at)
        attributes = self._attributes_for_span(span_data)
        operation = attributes.get(GenAI.GEN_AI_OPERATION_NAME, "operation")
        name = self._span_name(operation, attributes)
        kind = self._span_kind(span_data)

        with self._lock:
            parent_span = None
            if span.parent_id and span.parent_id in self._spans:
                parent_span = self._spans[span.parent_id].span
            elif span.trace_id in self._root_spans:
                parent_span = self._root_spans[span.trace_id]

            context = set_span_in_context(parent_span) if parent_span else None
            otel_span = self._tracer.start_span(
                name=name,
                kind=kind,
                attributes=attributes,
                start_time=start_time,
                context=context,
            )
            self._spans[span.span_id] = _SpanContext(span=otel_span, kind=kind)

    def on_span_end(self, span: AgentsSpan[Any]) -> None:
        end_time = _parse_iso8601(span.ended_at)

        with self._lock:
            context = self._spans.pop(span.span_id, None)

        if context is None:
            return

        otel_span = context.span
        if otel_span.is_recording():
            attributes = self._attributes_for_span(span.span_data)
            for key, value in attributes.items():
                otel_span.set_attribute(key, value)

            error = span.error
            if error:
                description = error.get("message") or ""
                otel_span.set_status(Status(StatusCode.ERROR, description))
            else:
                otel_span.set_status(Status(StatusCode.OK))

        otel_span.end(end_time=end_time)

    def shutdown(self) -> None:
        with self._lock:
            spans = list(self._spans.values())
            self._spans.clear()
            roots = list(self._root_spans.values())
            self._root_spans.clear()

        for context in spans:
            context.span.set_status(Status(StatusCode.ERROR, "shutdown"))
            context.span.end()

        for root in roots:
            root.set_status(Status(StatusCode.ERROR, "shutdown"))
            root.end()

    def force_flush(self) -> None:
        # no batching
        return


__all__ = ["_OpenAIAgentsSpanProcessor"]
