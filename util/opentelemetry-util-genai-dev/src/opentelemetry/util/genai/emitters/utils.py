# Shared utility functions for GenAI emitters (migrated from generators/utils.py)
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry._logs import (
    Logger,  # noqa: F401 (kept for backward compatibility if referenced externally)
)
from opentelemetry.metrics import Histogram
from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.types import AttributeValue

from ..attributes import (
    GEN_AI_EMBEDDINGS_DIMENSION_COUNT,
    GEN_AI_EMBEDDINGS_INPUT_TEXTS,
    GEN_AI_FRAMEWORK,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_ENCODING_FORMATS,
    SERVER_ADDRESS,
    SERVER_PORT,
)
from ..types import (
    AgentInvocation,
    EmbeddingInvocation,
    LLMInvocation,
    Task,
    Text,
    ToolCall,
    ToolCallResponse,
    Workflow,
)


def _serialize_messages(
    messages, exclude_system: bool = False
) -> Optional[str]:
    """Safely JSON serialize a sequence of dataclass messages.

    Uses the same format as events for consistency with semantic conventions.

    Args:
        messages: List of InputMessage or OutputMessage objects
        exclude_system: If True, exclude messages with role="system"

    Returns a JSON string or None on failure.
    """
    try:  # pragma: no cover - defensive
        serialized_msgs = []

        for msg in messages:
            # Skip system messages if exclude_system is True
            if exclude_system and msg.role == "system":
                continue

            msg_dict = {"role": msg.role, "parts": []}

            # Add finish_reason for output messages
            if hasattr(msg, "finish_reason"):
                msg_dict["finish_reason"] = msg.finish_reason or "stop"

            # Process parts (text, tool_call, tool_call_response)
            for part in msg.parts:
                if isinstance(part, Text):
                    part_dict = {
                        "type": "text",
                        "content": part.content,
                    }
                    msg_dict["parts"].append(part_dict)
                elif isinstance(part, ToolCall):
                    tool_dict = {
                        "type": "tool_call",
                        "id": part.id,
                        "name": part.name,
                        "arguments": part.arguments,
                    }
                    msg_dict["parts"].append(tool_dict)
                elif isinstance(part, ToolCallResponse):
                    tool_response_dict = {
                        "type": "tool_call_response",
                        "id": part.id,
                        "result": part.response,
                    }
                    msg_dict["parts"].append(tool_response_dict)
                else:
                    # Fallback for other part types
                    part_dict = (
                        asdict(part)
                        if hasattr(part, "__dataclass_fields__")
                        else part
                    )
                    msg_dict["parts"].append(part_dict)

            serialized_msgs.append(msg_dict)

        return json.dumps(serialized_msgs)
    except Exception:  # pragma: no cover
        return None


def _extract_system_instructions(messages) -> Optional[str]:
    """Extract and serialize system instructions from messages.

    Extracts messages with role="system" and serializes their parts.
    Uses the same format as events for consistency.

    Returns a JSON string or None if no system instructions found.
    """
    try:  # pragma: no cover - defensive
        system_parts = []

        for msg in messages:
            if msg.role == "system":
                for part in msg.parts:
                    if isinstance(part, Text):
                        part_dict = {
                            "type": "text",
                            "content": part.content,
                        }
                        system_parts.append(part_dict)
                    else:
                        # Fallback for other part types
                        part_dict = (
                            asdict(part)
                            if hasattr(part, "__dataclass_fields__")
                            else part
                        )
                        system_parts.append(part_dict)

        if system_parts:
            return json.dumps(system_parts)
        return None
    except Exception:  # pragma: no cover
        return None


def _apply_function_definitions(
    span: trace.Span, request_functions: Optional[List[dict]]
) -> None:
    """Apply request function definition attributes (idempotent).

    Shared between span emitters to avoid duplicated loops.
    """
    if not request_functions:
        return
    for idx, fn in enumerate(request_functions):
        try:
            name = fn.get("name")
            if name:
                span.set_attribute(f"gen_ai.request.function.{idx}.name", name)
            desc = fn.get("description")
            if desc:
                span.set_attribute(
                    f"gen_ai.request.function.{idx}.description", desc
                )
            params = fn.get("parameters")
            if params is not None:
                span.set_attribute(
                    f"gen_ai.request.function.{idx}.parameters", str(params)
                )
        except Exception:  # pragma: no cover - defensive
            pass


def _apply_llm_finish_semconv(
    span: trace.Span, invocation: LLMInvocation
) -> None:
    """Apply finish-time semantic convention attributes for an LLMInvocation.

    Includes response model/id, usage tokens, and function definitions (re-applied).
    """
    try:  # pragma: no cover - defensive
        if invocation.response_model_name:
            span.set_attribute(
                GenAI.GEN_AI_RESPONSE_MODEL, invocation.response_model_name
            )
        if invocation.response_id:
            span.set_attribute(
                GenAI.GEN_AI_RESPONSE_ID, invocation.response_id
            )
        if invocation.input_tokens is not None:
            span.set_attribute(
                GenAI.GEN_AI_USAGE_INPUT_TOKENS, invocation.input_tokens
            )
        if invocation.output_tokens is not None:
            span.set_attribute(
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, invocation.output_tokens
            )
        _apply_function_definitions(span, invocation.request_functions)
    except Exception:  # pragma: no cover
        pass


def _llm_invocation_to_log_record(
    invocation: LLMInvocation,
    capture_content: bool,
) -> Optional[SDKLogRecord]:
    """Create a log record for an LLM invocation"""
    attributes: Dict[str, Any] = {
        "event.name": "gen_ai.client.inference.operation.details",
    }
    if invocation.attributes.get("framework"):
        attributes[GEN_AI_FRAMEWORK] = invocation.attributes.get("framework")
    if invocation.provider:
        attributes[GEN_AI_PROVIDER_NAME] = invocation.provider
    if invocation.request_model:
        attributes["gen_ai.request.model"] = invocation.request_model

    # Optional attributes from semantic conventions table
    if invocation.response_model_name:
        attributes["gen_ai.response.model"] = invocation.response_model_name
    if invocation.response_id:
        attributes["gen_ai.response.id"] = invocation.response_id
    if invocation.input_tokens is not None:
        attributes["gen_ai.usage.input_tokens"] = invocation.input_tokens
    if invocation.output_tokens is not None:
        attributes["gen_ai.usage.output_tokens"] = invocation.output_tokens
    attr_mappings = {
        "gen_ai.request.id": "gen_ai.request.id",
        "gen_ai.request.max_tokens": "gen_ai.request.max_tokens",
        "gen_ai.request.temperature": "gen_ai.request.temperature",
        "gen_ai.request.top_p": "gen_ai.request.top_p",
        "gen_ai.request.top_k": "gen_ai.request.top_k",
        "gen_ai.request.frequency_penalty": "gen_ai.request.frequency_penalty",
        "gen_ai.request.presence_penalty": "gen_ai.request.presence_penalty",
        "gen_ai.request.stop_sequences": "gen_ai.request.stop_sequences",
        "gen_ai.response.finish_reasons": "gen_ai.response.finish_reasons",
        "gen_ai.request.choice.count": "gen_ai.request.choice.count",
    }

    for attr_key, semconv_key in attr_mappings.items():
        if attr_key in invocation.attributes:
            attributes[semconv_key] = invocation.attributes[attr_key]

    # If choice count not in attributes, infer from output_messages length
    if (
        "gen_ai.request.choice.count" not in attributes
        and invocation.output_messages
        and len(invocation.output_messages) != 1
    ):
        attributes["gen_ai.request.choice.count"] = len(
            invocation.output_messages
        )

    # Add agent context if available
    if invocation.agent_name:
        attributes["gen_ai.agent.name"] = invocation.agent_name
    if invocation.agent_id:
        attributes["gen_ai.agent.id"] = invocation.agent_id

    body: Dict[str, Any] = {}
    system_instructions = []

    if invocation.input_messages:
        input_msgs = []
        for msg in invocation.input_messages:
            if msg.role == "system":
                for part in msg.parts:
                    if isinstance(part, Text):
                        part_dict = {
                            "type": "text",
                            "content": part.content if capture_content else "",
                        }
                        system_instructions.append(part_dict)
                    else:
                        try:
                            part_dict = (
                                asdict(part)
                                if hasattr(part, "__dataclass_fields__")
                                else part
                            )
                            if (
                                not capture_content
                                and isinstance(part_dict, dict)
                                and "content" in part_dict
                            ):
                                part_dict["content"] = ""
                            system_instructions.append(part_dict)
                        except Exception:
                            pass
                continue  # Don't include in input_messages

            # Message structure: role and parts array
            input_msg = {"role": msg.role, "parts": []}

            # Process parts (text, tool_call, tool_call_response)
            for part in msg.parts:
                if isinstance(part, Text):
                    part_dict = {
                        "type": "text",
                        "content": part.content if capture_content else "",
                    }
                    input_msg["parts"].append(part_dict)
                elif isinstance(part, ToolCall):
                    tool_dict = {
                        "type": "tool_call",
                        "id": part.id,
                        "name": part.name,
                        "arguments": part.arguments if capture_content else {},
                    }
                    input_msg["parts"].append(tool_dict)
                elif isinstance(part, ToolCallResponse):
                    tool_response_dict = {
                        "type": "tool_call_response",
                        "id": part.id,
                        "result": part.response if capture_content else "",
                    }
                    input_msg["parts"].append(tool_response_dict)
                else:
                    try:
                        part_dict = (
                            asdict(part)
                            if hasattr(part, "__dataclass_fields__")
                            else part
                        )
                        if not capture_content and isinstance(part_dict, dict):
                            # Clear content fields
                            if "content" in part_dict:
                                part_dict["content"] = ""
                            if "arguments" in part_dict:
                                part_dict["arguments"] = {}
                            if "response" in part_dict:
                                part_dict["response"] = ""
                        input_msg["parts"].append(part_dict)
                    except Exception:
                        pass

            input_msgs.append(input_msg)

        if input_msgs:
            body["gen_ai.input.messages"] = input_msgs

    if system_instructions:
        body["gen_ai.system.instructions"] = system_instructions

    if invocation.output_messages:
        output_msgs = []

        for msg in invocation.output_messages:
            output_msg = {
                "role": msg.role,
                "parts": [],
                "finish_reason": msg.finish_reason or "stop",
            }

            # Process parts (text, tool_calls, etc.)
            for part in msg.parts:
                if isinstance(part, Text):
                    part_dict = {
                        "type": "text",
                        "content": part.content if capture_content else "",
                    }
                    output_msg["parts"].append(part_dict)
                elif isinstance(part, ToolCall):
                    tool_dict = {
                        "type": "tool_call",
                        "id": part.id,
                        "name": part.name,
                        "arguments": part.arguments if capture_content else {},
                    }
                    output_msg["parts"].append(tool_dict)
                else:
                    try:
                        part_dict = (
                            asdict(part)
                            if hasattr(part, "__dataclass_fields__")
                            else part
                        )
                        if not capture_content and isinstance(part_dict, dict):
                            # Clear content fields
                            if "content" in part_dict:
                                part_dict["content"] = ""
                            if "arguments" in part_dict:
                                part_dict["arguments"] = {}
                        output_msg["parts"].append(part_dict)
                    except Exception:
                        pass

            output_msgs.append(output_msg)
        body["gen_ai.output.messages"] = output_msgs

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.client.inference.operation.details",
    )


def _get_metric_attributes(
    request_model: Optional[str],
    response_model: Optional[str],
    operation_name: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> Dict[str, AttributeValue]:
    attributes: Dict[str, AttributeValue] = {}
    if framework is not None:
        attributes[GEN_AI_FRAMEWORK] = framework
    if system:
        # NOTE: The 'system' parameter historically mapped to provider name; keeping for backward compatibility.
        attributes[GEN_AI_PROVIDER_NAME] = system
    if operation_name:
        attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
    if request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
    if response_model:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model
    return attributes


def _record_token_metrics(
    token_histogram: Histogram,
    prompt_tokens: Optional[AttributeValue],
    completion_tokens: Optional[AttributeValue],
    metric_attributes: Dict[str, AttributeValue],
) -> None:
    prompt_attrs: Dict[str, AttributeValue] = {
        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.INPUT.value
    }
    prompt_attrs.update(metric_attributes)
    if isinstance(prompt_tokens, (int, float)):
        token_histogram.record(prompt_tokens, attributes=prompt_attrs)

    completion_attrs: Dict[str, AttributeValue] = {
        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.COMPLETION.value
    }
    completion_attrs.update(metric_attributes)
    if isinstance(completion_tokens, (int, float)):
        token_histogram.record(completion_tokens, attributes=completion_attrs)


def _record_duration(
    duration_histogram: Histogram,
    invocation: LLMInvocation | EmbeddingInvocation | ToolCall,
    metric_attributes: Dict[str, AttributeValue],
) -> None:
    if invocation.end_time is not None:
        elapsed: float = invocation.end_time - invocation.start_time
        duration_histogram.record(elapsed, attributes=metric_attributes)


# Helper functions for agentic types
def _workflow_to_log_record(
    workflow: Workflow, capture_content: bool
) -> Optional[SDKLogRecord]:
    """Create a log record for a workflow event."""
    attributes: Dict[str, Any] = {
        "event.name": "gen_ai.client.workflow.operation.details",
        "gen_ai.workflow.name": workflow.name,
    }

    if workflow.workflow_type:
        attributes["gen_ai.workflow.type"] = workflow.workflow_type
    if workflow.description:
        attributes["gen_ai.workflow.description"] = workflow.description
    if workflow.framework:
        attributes[GEN_AI_FRAMEWORK] = workflow.framework

    body: Dict[str, Any] = {}

    if capture_content:
        if workflow.initial_input:
            body["initial_input"] = workflow.initial_input
        if workflow.final_output:
            body["final_output"] = workflow.final_output

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.client.workflow.operation.details",
    )


def _agent_to_log_record(
    agent: AgentInvocation, capture_content: bool
) -> Optional[SDKLogRecord]:
    """Create a log record for agent event"""
    if not capture_content or not agent.system_instructions:
        return None

    attributes: Dict[str, Any] = {
        "event.name": "gen_ai.client.agent.operation.details",
        GEN_AI_FRAMEWORK: agent.framework,
    }

    attributes["gen_ai.agent.name"] = agent.name
    attributes["gen_ai.agent.id"] = str(agent.run_id)

    body = agent.system_instructions

    return SDKLogRecord(
        body=body,
        attributes=attributes,
        event_name="gen_ai.client.agent.operation.details",
    )


def _task_to_log_record(
    task: Task, capture_content: bool
) -> Optional[SDKLogRecord]:
    """Create a log record for a task event.

    Note: Task events are not yet in semantic conventions but follow
    the message structure pattern for consistency.
    """
    # Attributes contain metadata (not content)
    attributes: Dict[str, Any] = {
        "event.name": "gen_ai.client.task.operation.details",
        "gen_ai.task.name": task.name,
    }

    if task.task_type:
        attributes["gen_ai.task.type"] = task.task_type
    if task.objective:
        attributes["gen_ai.task.objective"] = task.objective
    if task.source:
        attributes["gen_ai.task.source"] = task.source
    if task.assigned_agent:
        attributes["gen_ai.agent.name"] = task.assigned_agent
    if task.status:
        attributes["gen_ai.task.status"] = task.status

    # Body contains messages/content only (following semantic conventions pattern)
    # If capture_content is disabled, emit empty content (like LLM messages do)
    body: Dict[str, Any] = {}

    if capture_content:
        if task.input_data:
            body["input_data"] = task.input_data
        if task.output_data:
            body["output_data"] = task.output_data
    else:
        # Emit structure with empty content when capture is disabled
        if task.input_data:
            body["input_data"] = ""
        if task.output_data:
            body["output_data"] = ""

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.client.task.operation.details",
    )


def _embedding_to_log_record(
    embedding: EmbeddingInvocation, capture_content: bool
) -> Optional[SDKLogRecord]:
    """Create a log record for an embedding event."""
    # Attributes contain metadata (not content)
    attributes: Dict[str, Any] = {
        "event.name": "gen_ai.client.embedding.operation.details",
    }

    # Core attributes
    if embedding.operation_name:
        attributes["gen_ai.operation.name"] = embedding.operation_name
    if embedding.provider:
        attributes[GEN_AI_PROVIDER_NAME] = embedding.provider
    if embedding.request_model:
        attributes["gen_ai.request.model"] = embedding.request_model

    # Optional attributes
    if embedding.dimension_count:
        attributes[GEN_AI_EMBEDDINGS_DIMENSION_COUNT] = (
            embedding.dimension_count
        )
    if embedding.input_tokens is not None:
        attributes["gen_ai.usage.input_tokens"] = embedding.input_tokens
    if embedding.server_address:
        attributes[SERVER_ADDRESS] = embedding.server_address
    if embedding.server_port:
        attributes[SERVER_PORT] = embedding.server_port
    if embedding.encoding_formats:
        attributes[GEN_AI_REQUEST_ENCODING_FORMATS] = (
            embedding.encoding_formats
        )
    if embedding.error_type:
        attributes["error.type"] = embedding.error_type

    # Add agent context if available
    if embedding.agent_name:
        attributes["gen_ai.agent.name"] = embedding.agent_name
    if embedding.agent_id:
        attributes["gen_ai.agent.id"] = embedding.agent_id

    # Body contains content (input texts)
    body: Dict[str, Any] = {}

    if embedding.input_texts:
        if capture_content:
            body[GEN_AI_EMBEDDINGS_INPUT_TEXTS] = embedding.input_texts
        else:
            # Emit structure with empty content when capture is disabled
            body[GEN_AI_EMBEDDINGS_INPUT_TEXTS] = []

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.client.embedding.operation.details",
    )
