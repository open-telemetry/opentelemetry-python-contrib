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

"""Patch functions for Claude Agent SDK instrumentation."""

import logging
import time
from typing import Any, Dict, List, Optional

from opentelemetry import context as otel_context
from opentelemetry.instrumentation.claude_agent_sdk.utils import (
    extract_usage_from_result_message,
    get_model_from_options_or_env,
    infer_provider_from_base_url,
)
from opentelemetry.trace import set_span_in_context
from ._extended_types import (
    ExecuteToolInvocation,
    InvokeAgentInvocation,
)
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    MessagePart,
    OutputMessage,
    Text,
    ToolCall,
    ToolCallResponse,
)

logger = logging.getLogger(__name__)

# Storage for tool runs managed by client (created from response stream)
# Key: tool_use_id, Value: tool_invocation
_client_managed_runs: Dict[str, ExecuteToolInvocation] = {}


def _clear_client_managed_runs() -> None:
    """Clear all client-managed tool runs.

    This should be called when a conversation ends to avoid memory leaks
    and to clean up any orphaned tool runs.
    """
    global _client_managed_runs

    try:
        # Use a dummy handler for cleanup since we can't access the real one
        # This is just to clear the tracking dictionary
        pass
    except Exception:
        # If we can't get the handler (e.g., instrumentation not initialized),
        # we still need to clear the tracking dictionary to prevent memory leaks.
        _client_managed_runs.clear()
        return

    # End any orphaned tool runs
    for tool_use_id, tool_invocation in list(_client_managed_runs.items()):
        try:
            handler.fail_execute_tool(
                tool_invocation,
                Error(
                    message="Tool run not completed (conversation ended)",
                    type=RuntimeError,
                ),
            )
        except Exception:
            # Ignore errors when failing orphaned tools during cleanup.
            # If the span is already ended or invalid, we don't want to crash.
            # Best effort cleanup: continue processing remaining tools.
            pass

    _client_managed_runs.clear()


def _extract_message_parts(msg: Any) -> List[Any]:
    """Extract parts (text + tool calls) from an AssistantMessage."""
    parts = []
    if not hasattr(msg, "content"):
        return parts

    for block in msg.content:
        block_type = type(block).__name__
        if block_type == "TextBlock":
            parts.append(Text(content=getattr(block, "text", "")))
        elif block_type == "ToolUseBlock":
            tool_call = ToolCall(
                id=getattr(block, "id", ""),
                name=getattr(block, "name", ""),
                arguments=getattr(block, "input", {}),
            )
            parts.append(tool_call)

    return parts


def _create_tool_spans_from_message(
    msg: Any,
    handler: Any,  # ExtendedTelemetryHandlerForClaude or similar
    agent_invocation: InvokeAgentInvocation,
    active_task_stack: List[Any],
    exclude_tool_names: Optional[List[str]] = None,
) -> None:
    """Create tool execution spans from ToolUseBlocks in an AssistantMessage.

    Tool spans are children of the active SubAgent span (if any), otherwise agent span.
    When a Task tool is created, it's pushed onto active_task_stack along with a SubAgent span.

    The stack structure is: [{"task": ExecuteToolInvocation, "subagent": InvokeAgentInvocation}, ...]
    """
    if not hasattr(msg, "content"):
        return

    exclude_tool_names = exclude_tool_names or []

    # Determine parent span: use active SubAgent span if exists, otherwise agent span
    parent_span = (
        active_task_stack[-1]["subagent"].span
        if active_task_stack
        else agent_invocation.span
    )

    parent_context_token = None
    if parent_span:
        try:
            parent_context_token = otel_context.attach(
                set_span_in_context(parent_span)
            )
        except Exception:
            # If attaching the parent context fails, continue without it.
            # Instrumentation must not break the host application.
            pass

    try:
        for block in msg.content:
            if type(block).__name__ != "ToolUseBlock":
                continue

            tool_use_id = getattr(block, "id", None)
            tool_name = getattr(block, "name", "unknown_tool")
            tool_input = getattr(block, "input", {})

            if not tool_use_id or tool_name in exclude_tool_names:
                continue

            try:
                tool_invocation = ExecuteToolInvocation(
                    tool_name=tool_name,
                    tool_call_id=tool_use_id,
                    tool_call_arguments=tool_input,
                    tool_description=tool_name,
                )
                handler.start_execute_tool(tool_invocation)
                _client_managed_runs[tool_use_id] = tool_invocation

                # If this is a Task tool, create a SubAgent span under it
                # https://platform.claude.com/docs/en/agent-sdk/python#task
                if tool_name == "Task":
                    # Extract subagent_type from tool input
                    subagent_type = tool_input.get("subagent_type", "unknown")
                    task_description = tool_input.get("description", "")
                    task_prompt = tool_input.get("prompt", "")

                    # Create SubAgent span as child of Task Tool span
                    subagent_context_token = None
                    if tool_invocation.span:
                        try:
                            subagent_context_token = otel_context.attach(
                                set_span_in_context(tool_invocation.span)
                            )
                        except Exception:
                            # Context attachment failure should not break instrumentation
                            pass

                    try:
                        # Create input message from task prompt
                        input_messages = []
                        if task_prompt:
                            input_messages.append(
                                InputMessage(
                                    role="user",
                                    parts=[Text(content=task_prompt)],
                                )
                            )

                        # Create SubAgent invocation
                        subagent_invocation = InvokeAgentInvocation(
                            provider=infer_provider_from_base_url(),
                            agent_name=subagent_type,
                            agent_description=task_description,
                            input_messages=input_messages,
                        )

                        # Start SubAgent span
                        handler.start_invoke_agent(subagent_invocation)

                        # Push both Task and SubAgent onto stack as a dict
                        active_task_stack.append(
                            {
                                "task": tool_invocation,
                                "subagent": subagent_invocation,
                                "tool_use_id": tool_use_id,
                            }
                        )

                        logger.debug(
                            f"Task span created with SubAgent '{subagent_type}': {tool_use_id}, stack depth: {len(active_task_stack)}"
                        )
                    finally:
                        if subagent_context_token is not None:
                            try:
                                otel_context.detach(subagent_context_token)
                            except Exception:
                                # Context detachment failure should not break instrumentation
                                pass

            except Exception as e:
                logger.warning(
                    f"Failed to create tool span for {tool_name}: {e}"
                )
    finally:
        if parent_context_token is not None:
            try:
                otel_context.detach(parent_context_token)
            except Exception:
                # Context detachment failure should not break instrumentation
                pass


def _update_token_usage(
    agent_invocation: InvokeAgentInvocation,
    turn_tracker: "AssistantTurnTracker",
    msg: Any,
) -> None:
    """Update token usage from a ResultMessage."""
    usage_meta = extract_usage_from_result_message(msg)
    if not usage_meta:
        return

    # Update agent invocation token usage
    if "input_tokens" in usage_meta:
        agent_invocation.input_tokens = usage_meta["input_tokens"]
    if "output_tokens" in usage_meta:
        agent_invocation.output_tokens = usage_meta["output_tokens"]

    # Update current LLM turn token usage
    turn_tracker.update_usage(
        usage_meta.get("input_tokens"), usage_meta.get("output_tokens")
    )


def _process_assistant_message(
    msg: Any,
    model: str,
    prompt: str,
    agent_invocation: InvokeAgentInvocation,
    turn_tracker: "AssistantTurnTracker",
    handler: Any,  # ExtendedTelemetryHandlerForClaude
    collected_messages: List[Dict[str, Any]],
    active_task_stack: List[Any],
) -> None:
    """Process AssistantMessage: create LLM turn, extract parts, create tool spans."""
    parts = _extract_message_parts(msg)
    has_text_content = any(isinstance(p, Text) for p in parts)
    has_tool_calls = any(isinstance(p, ToolCall) for p in parts)

    # Check if we're inside a Task
    is_inside_task = len(active_task_stack) > 0

    if has_text_content:
        if turn_tracker.current_llm_invocation:
            turn_tracker.close_llm_turn()

        message_arrival_time = time.time()

        turn_tracker.start_llm_turn(
            msg,
            model,
            prompt,
            collected_messages,
            provider=infer_provider_from_base_url(),
            message_arrival_time=message_arrival_time,
            agent_invocation=agent_invocation,
        )

        if parts:
            turn_tracker.add_assistant_output(parts)
            output_msg = OutputMessage(
                role="assistant", parts=list(parts), finish_reason="stop"
            )
            agent_invocation.output_messages.append(output_msg)

            # Only add to collected_messages if not inside a Task
            if not is_inside_task:
                collected_messages.append(
                    {"role": "assistant", "parts": list(parts)}
                )

    elif has_tool_calls:
        if parts and turn_tracker.current_llm_invocation:
            if turn_tracker.current_llm_invocation.output_messages:
                last_output_msg = (
                    turn_tracker.current_llm_invocation.output_messages[-1]
                )
                last_output_msg.parts.extend(parts)
                last_output_msg.finish_reason = "tool_calls"
            else:
                turn_tracker.add_assistant_output(parts)
                output_msg = OutputMessage(
                    role="assistant",
                    parts=list(parts),
                    finish_reason="tool_calls",
                )
                turn_tracker.current_llm_invocation.output_messages.append(
                    output_msg
                )

        # Only add to collected_messages if not inside a Task
        if not is_inside_task:
            if parts and collected_messages:
                last_msg = collected_messages[-1]
                if (
                    last_msg.get("role") == "assistant"
                    and turn_tracker.current_llm_invocation
                ):
                    last_parts = last_msg.get("parts", [])
                    last_parts.extend(parts)
                    last_msg["parts"] = last_parts
                else:
                    collected_messages.append(
                        {"role": "assistant", "parts": list(parts)}
                    )
            elif parts:
                collected_messages.append(
                    {"role": "assistant", "parts": list(parts)}
                )

    # Close LLM turn before creating tool spans to ensure correct timeline
    if has_tool_calls and turn_tracker.current_llm_invocation:
        turn_tracker.close_llm_turn()

    _create_tool_spans_from_message(
        msg, handler, agent_invocation, active_task_stack
    )


def _process_user_message(
    msg: Any,
    turn_tracker: "AssistantTurnTracker",
    handler: Any,  # ExtendedTelemetryHandlerForClaude
    collected_messages: List[Dict[str, Any]],
    active_task_stack: List[Any],
) -> None:
    """Process UserMessage: close tool spans, collect message content, mark next LLM start."""
    user_parts: List[MessagePart] = []
    tool_parts: List[MessagePart] = []

    msg_tool_use_result = getattr(msg, "tool_use_result", None)

    if hasattr(msg, "content"):
        for block in msg.content:
            block_type = type(block).__name__

            if block_type == "ToolResultBlock":
                tool_use_id = getattr(block, "tool_use_id", None)
                if tool_use_id and tool_use_id in _client_managed_runs:
                    tool_invocation = _client_managed_runs.pop(tool_use_id)

                    # Set tool response
                    tool_content = getattr(block, "content", None)
                    # tool_use_result is on the UserMessage, not on ToolResultBlock!
                    tool_use_result = msg_tool_use_result
                    is_error_value = getattr(block, "is_error", None)
                    is_error = is_error_value is True

                    tool_invocation.tool_call_result = tool_content

                    # Check if this is a Task tool result - if so, close SubAgent FIRST
                    # BEFORE closing the Task tool span
                    # https://platform.claude.com/docs/en/agent-sdk/python#task
                    is_task_result = (
                        active_task_stack
                        and active_task_stack[-1]["tool_use_id"] == tool_use_id
                    )
                    if is_task_result:
                        task_entry = active_task_stack.pop()

                        # Extract information from tool_use_result (official Task tool output format)
                        if tool_use_result and isinstance(
                            tool_use_result, dict
                        ):
                            agent_id = tool_use_result.get("agentId")
                            if agent_id:
                                task_entry["subagent"].agent_id = agent_id

                            # Extract result for output_messages
                            content_blocks = tool_use_result.get("content")
                            if content_blocks and isinstance(
                                content_blocks, list
                            ):
                                # Convert content blocks to Text parts
                                text_parts = []
                                for content_block in content_blocks:
                                    if isinstance(content_block, dict):
                                        if content_block.get("type") == "text":
                                            text_content = content_block.get(
                                                "text"
                                            )
                                            if text_content:
                                                text_parts.append(
                                                    Text(content=text_content)
                                                )

                                if text_parts:
                                    task_entry[
                                        "subagent"
                                    ].output_messages.append(
                                        OutputMessage(
                                            role="assistant",
                                            parts=text_parts,
                                            finish_reason="stop",
                                        )
                                    )

                            # Extract usage from tool_use_result
                            # Always record usage info from official SDK, even if values are 0
                            usage = tool_use_result.get("usage")
                            if usage and isinstance(usage, dict):
                                if "input_tokens" in usage:
                                    task_entry[
                                        "subagent"
                                    ].input_tokens = usage["input_tokens"]
                                if "output_tokens" in usage:
                                    task_entry[
                                        "subagent"
                                    ].output_tokens = usage["output_tokens"]
                        else:
                            logger.warning(
                                f"[SubAgent] tool_use_result is not a dict: {type(tool_use_result)}, value: {tool_use_result}"
                            )

                        # Close SubAgent span first (detach SubAgent context)
                        # This restores context to Task Tool span level
                        try:
                            handler.stop_invoke_agent(task_entry["subagent"])
                        except Exception as e:
                            logger.warning(
                                f"Failed to close SubAgent span: {e}"
                            )

                    # Now close the tool span (Task or regular tool)
                    # For Task: this detaches Task Tool context, restoring to Agent context
                    if is_error:
                        error_msg = (
                            str(tool_content)
                            if tool_content
                            else "Tool execution error"
                        )
                        handler.fail_execute_tool(
                            tool_invocation,
                            Error(message=error_msg, type=RuntimeError),
                        )
                    else:
                        handler.stop_execute_tool(tool_invocation)

                if tool_use_id:
                    tool_parts.append(
                        ToolCallResponse(
                            id=tool_use_id,
                            response=tool_content if tool_content else "",
                        )
                    )

            elif block_type == "TextBlock":
                text_content = getattr(block, "text", "")
                if text_content:
                    user_parts.append(Text(content=text_content))

    # This ensures Task tool results are NOT filtered out
    is_inside_task = len(active_task_stack) > 0

    # Only add to collected_messages if not inside a Task
    if not is_inside_task:
        if user_parts:
            collected_messages.append({"role": "user", "parts": user_parts})

        if tool_parts:
            if collected_messages:
                last_msg = collected_messages[-1]
                if (
                    last_msg.get("role") == "tool"
                    and turn_tracker.current_llm_invocation
                ):
                    last_parts = last_msg.get("parts", [])
                    last_parts.extend(tool_parts)
                    last_msg["parts"] = last_parts
                else:
                    collected_messages.append(
                        {"role": "tool", "parts": tool_parts}
                    )
            else:
                collected_messages.append(
                    {"role": "tool", "parts": tool_parts}
                )
    # Always mark next LLM start when UserMessage arrives
    turn_tracker.mark_next_llm_start()


def _process_system_message(
    msg: Any,
    agent_invocation: InvokeAgentInvocation,
) -> None:
    """Process SystemMessage: extract session_id early in the stream.

    SystemMessage appears at the beginning of the message stream and contains
    the session_id in its data field. We extract it here so that it's available
    for all subsequent LLM spans.
    """
    if hasattr(msg, "subtype") and msg.subtype == "init":
        if hasattr(msg, "data") and isinstance(msg.data, dict):
            session_id = msg.data.get("session_id")
            if session_id:
                agent_invocation.conversation_id = session_id


def _process_result_message(
    msg: Any,
    agent_invocation: InvokeAgentInvocation,
    turn_tracker: "AssistantTurnTracker",
) -> None:
    """Process ResultMessage: update session_id (fallback), token usage, and close any open LLM turn."""

    _update_token_usage(agent_invocation, turn_tracker, msg)

    if turn_tracker.current_llm_invocation:
        turn_tracker.close_llm_turn()


async def _process_agent_invocation_stream(
    wrapped_stream,
    handler: Any,  # ExtendedTelemetryHandlerForClaude
    model: str,
    prompt: str,
) -> Any:
    """Unified handler for processing agent invocation stream.

    Yields:
        Messages from the wrapped stream
    """
    agent_invocation = InvokeAgentInvocation(
        provider=infer_provider_from_base_url(),
        agent_name="claude-agent",
        request_model=model,
        conversation_id="",
        input_messages=[
            InputMessage(role="user", parts=[Text(content=prompt)])
        ]
        if prompt
        else [],
    )

    # Attach empty context to clear any previous context, ensuring each query
    # creates an independent root trace. This is important for scenarios where
    # multiple queries are called in the same script - each should have its own trace_id.
    empty_context_token = otel_context.attach(otel_context.Context())
    handler.start_invoke_agent(agent_invocation)

    query_start_time = time.time()
    turn_tracker = AssistantTurnTracker(
        handler, query_start_time=query_start_time
    )

    collected_messages: List[Dict[str, Any]] = []

    # Stack to track active Task tool invocations
    # When a Task tool is created, it's pushed here
    # When its ToolResultBlock is received, it's popped
    active_task_stack: List[Any] = []

    try:
        async for msg in wrapped_stream:
            msg_type = type(msg).__name__

            if msg_type == "SystemMessage":
                _process_system_message(msg, agent_invocation)
            elif msg_type == "AssistantMessage":
                _process_assistant_message(
                    msg,
                    model,
                    prompt,
                    agent_invocation,
                    turn_tracker,
                    handler,
                    collected_messages,
                    active_task_stack,
                )
            elif msg_type == "UserMessage":
                _process_user_message(
                    msg,
                    turn_tracker,
                    handler,
                    collected_messages,
                    active_task_stack,
                )
            elif msg_type == "ResultMessage":
                _process_result_message(msg, agent_invocation, turn_tracker)

            yield msg

        handler.stop_invoke_agent(agent_invocation)

    except Exception as e:
        error_msg = str(e)
        if agent_invocation.span:
            agent_invocation.span.set_attribute("error.type", type(e).__name__)
            agent_invocation.span.set_attribute("error.message", error_msg)
        handler.fail_invoke_agent(
            agent_invocation, error=Error(message=error_msg, type=type(e))
        )

        raise
    finally:
        turn_tracker.close()

        # Clean up any remaining Task spans in stack (shouldn't happen in normal flow)
        while active_task_stack:
            task_entry = active_task_stack.pop()
            logger.warning(
                f"Unclosed Task span at end of invocation: {task_entry['tool_use_id']}"
            )
            # Close SubAgent span if it exists
            try:
                handler.stop_invoke_agent(task_entry["subagent"])
            except Exception:
                # Span closure failure should not break the application
                pass

        # Detach empty context token to restore the original context.
        # Note: stop_invoke_agent/fail_invoke_agent already detached invocation.context_token,
        # which restored to empty context. Now we detach empty_context_token to restore further.
        otel_context.detach(empty_context_token)
        _clear_client_managed_runs()


class AssistantTurnTracker:
    """Track LLM invocations (assistant turns) in a Claude Agent conversation."""

    def __init__(
        self,
        handler: Any,  # ExtendedTelemetryHandlerForClaude
        query_start_time: Optional[float] = None,
    ):
        self.handler = handler
        self.current_llm_invocation: Optional[LLMInvocation] = None
        self.last_closed_llm_invocation: Optional[LLMInvocation] = None
        self.next_llm_start_time: Optional[float] = query_start_time

    def start_llm_turn(
        self,
        msg: Any,
        model: str,
        prompt: str,
        collected_messages: List[Dict[str, Any]],
        provider: str = "anthropic",
        message_arrival_time: Optional[float] = None,
        agent_invocation: Optional[InvokeAgentInvocation] = None,
    ) -> Optional[LLMInvocation]:
        """Start a new LLM invocation span with pre-recorded start time.

        Args:
            message_arrival_time: The time when the AssistantMessage arrived.
                If next_llm_start_time is set (from previous UserMessage), use that.
                Otherwise, use message_arrival_time or fall back to current time.
            agent_invocation: The parent agent invocation, used to extract conversation_id.
        """
        # Priority: next_llm_start_time > message_arrival_time > current time
        start_time = (
            self.next_llm_start_time or message_arrival_time or time.time()
        )

        if self.current_llm_invocation:
            self.handler.stop_llm(self.current_llm_invocation)
            self.last_closed_llm_invocation = self.current_llm_invocation
            self.current_llm_invocation = None

        self.next_llm_start_time = None

        input_messages = []

        if prompt:
            input_messages.append(
                InputMessage(role="user", parts=[Text(content=prompt)])
            )

        for hist_msg in collected_messages:
            role = hist_msg.get("role", "user")

            if "parts" in hist_msg:
                parts = hist_msg["parts"]
                if parts:
                    input_messages.append(InputMessage(role=role, parts=parts))
            elif "content" in hist_msg:
                content = hist_msg["content"]
                if isinstance(content, str) and content:
                    input_messages.append(
                        InputMessage(role=role, parts=[Text(content=content)])
                    )

        llm_invocation = LLMInvocation(
            provider=provider,
            request_model=model,
            input_messages=input_messages,
        )

        # Add conversation_id (session_id) to LLM span attributes
        # This is a custom extension beyond standard GenAI semantic conventions
        if agent_invocation and agent_invocation.conversation_id:
            llm_invocation.attributes["gen_ai.conversation.id"] = (
                agent_invocation.conversation_id
            )

        self.handler.start_llm(llm_invocation)
        # TODO(telemetry): Use public API for setting span start time
        if llm_invocation.span and start_time:
            start_time_ns = int(start_time * 1_000_000_000)
            try:
                if hasattr(llm_invocation.span, "_start_time"):
                    setattr(llm_invocation.span, "_start_time", start_time_ns)
            except Exception as e:
                logger.warning(f"Failed to set span start time: {e}")

        self.current_llm_invocation = llm_invocation
        return llm_invocation

    def add_assistant_output(self, parts: List[Any]) -> None:
        """Add output message parts to current LLM invocation."""
        if not self.current_llm_invocation or not parts:
            return

        output_msg = OutputMessage(
            role="assistant", parts=list(parts), finish_reason="stop"
        )
        self.current_llm_invocation.output_messages.append(output_msg)

    def mark_next_llm_start(self) -> None:
        """Mark the start time for the next LLM invocation."""
        self.next_llm_start_time = time.time()

    def update_usage(
        self, input_tokens: Optional[int], output_tokens: Optional[int]
    ) -> None:
        """Update token usage for current or last closed LLM invocation."""
        target_invocation = (
            self.current_llm_invocation or self.last_closed_llm_invocation
        )
        if not target_invocation:
            return

        if input_tokens is not None:
            target_invocation.input_tokens = input_tokens
        if output_tokens is not None:
            target_invocation.output_tokens = output_tokens

    def close_llm_turn(self) -> None:
        """Close the current LLM invocation span."""
        if self.current_llm_invocation:
            self.handler.stop_llm(self.current_llm_invocation)
            self.last_closed_llm_invocation = self.current_llm_invocation
            self.current_llm_invocation = None

    def close(self) -> None:
        """Close any open LLM invocation (cleanup fallback)."""
        if self.current_llm_invocation:
            self.handler.stop_llm(self.current_llm_invocation)
            self.current_llm_invocation = None


def wrap_claude_client_init(wrapped, instance, args, kwargs, handler=None):
    """Wrapper for ClaudeSDKClient.__init__ to inject tracing hooks."""
    if handler is None:
        logger.warning("Handler not provided, skipping instrumentation")
        return wrapped(*args, **kwargs)

    result = wrapped(*args, **kwargs)

    instance._otel_handler = handler
    instance._otel_prompt = None

    return result


def wrap_claude_client_query(wrapped, instance, args, kwargs, handler=None):
    """Wrapper for ClaudeSDKClient.query to capture prompt."""
    if hasattr(instance, "_otel_prompt"):
        instance._otel_prompt = str(
            kwargs.get("prompt") or (args[0] if args else "")
        )

    return wrapped(*args, **kwargs)


async def wrap_claude_client_receive_response(
    wrapped, instance, args, kwargs, handler=None
):
    """Wrapper for ClaudeSDKClient.receive_response to trace agent invocation."""
    if handler is None:
        handler = getattr(instance, "_otel_handler", None)

    if handler is None:
        logger.warning("Handler not available, skipping instrumentation")
        async for msg in wrapped(*args, **kwargs):
            yield msg
        return

    prompt = getattr(instance, "_otel_prompt", "") or ""
    model = "unknown"
    if hasattr(instance, "options") and instance.options:
        model = get_model_from_options_or_env(instance.options)

    async for msg in _process_agent_invocation_stream(
        wrapped(*args, **kwargs),
        handler=handler,
        model=model,
        prompt=prompt,
    ):
        yield msg


async def wrap_query(wrapped, instance, args, kwargs, handler=None):
    """Wrapper for claude_agent_sdk.query() standalone function."""
    if handler is None:
        logger.warning("Handler not provided, skipping instrumentation")
        async for message in wrapped(*args, **kwargs):
            yield message
        return

    prompt = kwargs.get("prompt") or (args[0] if args else "")
    options = kwargs.get("options")

    model = get_model_from_options_or_env(options)
    prompt_str = str(prompt) if isinstance(prompt, str) else ""

    async for message in _process_agent_invocation_stream(
        wrapped(*args, **kwargs),
        handler=handler,
        model=model,
        prompt=prompt_str,
    ):
        yield message
