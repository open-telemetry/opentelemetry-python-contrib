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

from __future__ import annotations

import json
import logging
import threading
import timeit
from typing import Any, Optional, cast
from uuid import UUID

from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from opentelemetry.instrumentation.langchain.content_recording import (
    get_content_policy,
    should_record_retriever_content,
    should_record_tool_content,
)
from opentelemetry.instrumentation.langchain.event_emitter import EventEmitter
from opentelemetry.instrumentation.langchain.invocation_manager import (
    _InvocationManager,
)
from opentelemetry.instrumentation.langchain.message_formatting import (
    format_documents,
    prepare_messages,
    serialize_tool_result,
)
from opentelemetry.instrumentation.langchain.operation_mapping import (
    OperationName,
    classify_chain_run,
    resolve_agent_name,
)
from opentelemetry.instrumentation.langchain.semconv_attributes import (
    GEN_AI_WORKFLOW_NAME,
    METRIC_TIME_PER_OUTPUT_CHUNK,
    METRIC_TIME_TO_FIRST_CHUNK,
    OP_EXECUTE_TOOL,
)
from opentelemetry.instrumentation.langchain.span_manager import (
    _SpanManager,
)
from opentelemetry.instrumentation.langchain.utils import (
    extract_propagation_context,
    infer_provider_name,
    infer_server_address,
    infer_server_port,
    propagated_context,
)
from opentelemetry.metrics import get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    MessagePart,
    OutputMessage,
    Text,
)

logger = logging.getLogger(__name__)


def _has_goto(output: Any) -> bool:
    """Detect LangGraph ``Command(goto=...)`` patterns in chain/tool output.

    LangGraph ``Command`` objects have both ``.goto`` and ``.update``
    attributes.  The output may be the object directly, wrapped in a
    dict, or inside a list/tuple.
    """
    if output is None:
        return False

    # Direct Command-like object
    if hasattr(output, "goto") and hasattr(output, "update"):
        return bool(getattr(output, "goto", None))

    # Dict — check for "goto" key or Command-like values
    if isinstance(output, dict):
        if output.get("goto"):
            return True
        for val in output.values():
            if hasattr(val, "goto") and hasattr(val, "update"):
                if getattr(val, "goto", None):
                    return True

    # List/tuple — check elements
    if isinstance(output, (list, tuple)):
        for item in output:
            if hasattr(item, "goto") and hasattr(item, "update"):
                if getattr(item, "goto", None):
                    return True

    return False


def _extract_chain_messages(data: Any) -> Any:
    """Extract message content from chain inputs or outputs.

    LangChain stores messages under various keys depending on the
    chain type.  Returns the first non-None value found, or ``None``.
    """
    if not isinstance(data, dict):
        return data

    for key in (
        "messages",
        "input",
        "output",
        "question",
        "query",
        "result",
        "answer",
        "response",
    ):
        value = data.get(key)
        if value is not None:
            return value

    return None


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    def __init__(
        self,
        telemetry_handler: TelemetryHandler,
        span_manager: Optional[_SpanManager] = None,
        event_emitter: Optional[EventEmitter] = None,
    ) -> None:
        super().__init__()
        self._telemetry_handler = telemetry_handler
        self._span_manager = span_manager
        self._event_emitter = event_emitter
        self._invocation_manager = _InvocationManager()

        # Streaming state: str(run_id) → monotonic timestamp of the last chunk
        self._streaming_state: dict[str, float] = {}
        self._streaming_lock = threading.Lock()

        # The TelemetryHandler handles duration and token usage metrics.
        # Streaming metrics are not yet in the shared handler, so we create
        # them here using the same meter.
        meter = get_meter(__name__)
        self._ttfc_histogram = meter.create_histogram(
            name=METRIC_TIME_TO_FIRST_CHUNK,
            description="Time to generate first chunk in a streaming response",
            unit="s",
        )
        self._tpoc_histogram = meter.create_histogram(
            name=METRIC_TIME_PER_OUTPUT_CHUNK,
            description="Time between consecutive chunks in a streaming response",
            unit="s",
        )

    def _handle_model_start(
        self,
        serialized: dict[str, Any],
        input_messages: list[InputMessage],
        operation_name: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Shared logic for on_chat_model_start and on_llm_start."""
        if "invocation_params" in kwargs:
            params = (
                kwargs["invocation_params"].get("params")
                or kwargs["invocation_params"]
            )
        else:
            params = kwargs

        request_model = "unknown"
        for model_tag in (
            "model_name",
            "model_id",
            "model",
            "engine",
            "deployment_name",
        ):
            if (model := (params or {}).get(model_tag)) is not None:
                request_model = model
                break
            elif (model := (metadata or {}).get(model_tag)) is not None:
                request_model = model
                break

        # Initialize variables with default values to avoid "possibly unbound" errors
        top_p = None
        frequency_penalty = None
        presence_penalty = None
        stop_sequences = None
        seed = None
        temperature = None
        max_tokens = None

        if params is not None:
            top_p = params.get("top_p")
            frequency_penalty = params.get("frequency_penalty")
            presence_penalty = params.get("presence_penalty")
            stop_sequences = params.get("stop")
            seed = params.get("seed")
            temperature = params.get("temperature")
            max_tokens = params.get("max_completion_tokens")

        invocation_params = kwargs.get("invocation_params") or {}
        provider = infer_provider_name(serialized, metadata, invocation_params)
        if provider is None:
            provider = "unknown"

        if metadata is not None:
            # Override with metadata values if present (e.g. ChatBedrock)
            if "ls_temperature" in metadata:
                temperature = metadata.get("ls_temperature")
            if "ls_max_tokens" in metadata:
                max_tokens = metadata.get("ls_max_tokens")

        server_address = infer_server_address(serialized, invocation_params)
        server_port = infer_server_port(serialized, invocation_params)

        # Additional semconv request attributes
        extra_attrs: dict[str, Any] = {}

        top_k = params.get("top_k") if params else None
        if top_k is not None:
            extra_attrs[GenAI.GEN_AI_REQUEST_TOP_K] = top_k

        # Choice count (n) — only set if != 1
        choice_count = params.get("n") if params else None
        if isinstance(choice_count, int) and choice_count != 1:
            extra_attrs[GenAI.GEN_AI_REQUEST_CHOICE_COUNT] = choice_count

        # Output type from response_format
        if params:
            response_format = params.get("response_format")
            if isinstance(response_format, dict):
                output_type = response_format.get("type")
                if output_type is not None:
                    extra_attrs[GenAI.GEN_AI_OUTPUT_TYPE] = output_type
            elif isinstance(response_format, str):
                extra_attrs[GenAI.GEN_AI_OUTPUT_TYPE] = response_format

        # Encoding formats
        encoding_format = params.get("encoding_format") if params else None
        if encoding_format is not None:
            extra_attrs[GenAI.GEN_AI_REQUEST_ENCODING_FORMATS] = [
                encoding_format
            ]

        llm_invocation = LLMInvocation(
            operation_name=operation_name,
            request_model=request_model,
            input_messages=input_messages,
            provider=provider,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop_sequences=stop_sequences,
            seed=seed,
            temperature=temperature,
            max_tokens=max_tokens,
            server_address=server_address,
            server_port=server_port,
            attributes=extra_attrs,
        )
        llm_invocation = self._telemetry_handler.start_llm(
            invocation=llm_invocation
        )
        self._invocation_manager.add_invocation_state(
            run_id=run_id,
            parent_run_id=parent_run_id,
            invocation=llm_invocation,
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        input_messages: list[InputMessage] = []
        for sub_messages in messages:
            for message in sub_messages:
                # Cast to Any to avoid type checking issues with LangChain's complex content type
                raw_content: Any = message.content  # type: ignore[misc]
                role = message.type
                parts: list[Text] = []

                if isinstance(raw_content, str):
                    parts = [Text(content=raw_content, type="text")]
                elif isinstance(raw_content, list):
                    for item in raw_content:  # type: ignore[misc]
                        if isinstance(item, str):
                            parts.append(Text(content=item, type="text"))
                        elif isinstance(item, dict):
                            # Safely extract text content from dict
                            text_value = item.get("text")  # type: ignore[misc]
                            if isinstance(text_value, str) and text_value:
                                parts.append(
                                    Text(content=text_value, type="text")
                                )

                input_messages.append(
                    InputMessage(
                        parts=cast(list[MessagePart], parts), role=role
                    )
                )

        self._handle_model_start(
            serialized,
            input_messages,
            "chat",
            run_id=run_id,
            parent_run_id=parent_run_id,
            metadata=metadata,
            **kwargs,
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        input_messages: list[InputMessage] = [
            InputMessage(
                role="user",
                parts=cast(
                    list[MessagePart], [Text(content=prompt, type="text")]
                ),
            )
            for prompt in prompts
        ]

        self._handle_model_start(
            serialized,
            input_messages,
            "text_completion",
            run_id=run_id,
            parent_run_id=parent_run_id,
            metadata=metadata,
            **kwargs,
        )

    def on_llm_new_token(
        self,
        token: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        invocation = self._invocation_manager.get_invocation(run_id)
        if invocation is None or not isinstance(invocation, LLMInvocation):
            return

        now = timeit.default_timer()
        started_at = invocation.monotonic_start_s
        if started_at is None:
            return

        # Build metric attributes matching InvocationMetricsRecorder's pattern
        metric_attrs: dict[str, Any] = {}
        if invocation.operation_name:
            metric_attrs[GenAI.GEN_AI_OPERATION_NAME] = (
                invocation.operation_name
            )
        if invocation.request_model:
            metric_attrs[GenAI.GEN_AI_REQUEST_MODEL] = invocation.request_model
        if invocation.provider:
            metric_attrs[GenAI.GEN_AI_PROVIDER_NAME] = invocation.provider
        if invocation.response_model_name:
            metric_attrs[GenAI.GEN_AI_RESPONSE_MODEL] = (
                invocation.response_model_name
            )
        if invocation.server_address:
            metric_attrs[server_attributes.SERVER_ADDRESS] = (
                invocation.server_address
            )
        if invocation.server_port is not None:
            metric_attrs[server_attributes.SERVER_PORT] = (
                invocation.server_port
            )

        run_key = str(run_id)
        with self._streaming_lock:
            last_chunk_at = self._streaming_state.get(run_key)
            self._streaming_state[run_key] = now

        if last_chunk_at is None:
            # First token — record time to first chunk
            self._ttfc_histogram.record(
                max(now - started_at, 0.0), attributes=metric_attrs
            )
        else:
            # Subsequent token — record time per output chunk
            self._tpoc_histogram.record(
                max(now - last_chunk_at, 0.0), attributes=metric_attrs
            )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        llm_invocation = self._invocation_manager.get_invocation(run_id=run_id)
        if llm_invocation is None or not isinstance(
            llm_invocation, LLMInvocation
        ):
            # If the invocation does not exist, we cannot set attributes or end it
            return

        output_messages: list[OutputMessage] = []
        for generation in getattr(response, "generations", []):
            for chat_generation in generation:
                # Get finish reason
                finish_reason = "unknown"  # Default value
                generation_info = getattr(
                    chat_generation, "generation_info", None
                )
                if generation_info is not None:
                    finish_reason = generation_info.get(
                        "finish_reason", "unknown"
                    )

                if chat_generation.message:
                    # Get finish reason if generation_info is None above
                    if (
                        generation_info is None
                        and chat_generation.message.response_metadata
                    ):
                        finish_reason = (
                            chat_generation.message.response_metadata.get(
                                "stopReason", "unknown"
                            )
                        )

                    # Get message content
                    parts = [
                        Text(
                            content=chat_generation.message.content,
                            type="text",
                        )
                    ]
                    role = chat_generation.message.type
                    output_message = OutputMessage(
                        role=role,
                        parts=cast(list[MessagePart], parts),
                        finish_reason=finish_reason,
                    )
                    output_messages.append(output_message)

                    # Get token usage if available
                    if chat_generation.message.usage_metadata:
                        input_tokens = (
                            chat_generation.message.usage_metadata.get(
                                "input_tokens", 0
                            )
                        )
                        llm_invocation.input_tokens = input_tokens

                        output_tokens = (
                            chat_generation.message.usage_metadata.get(
                                "output_tokens", 0
                            )
                        )
                        llm_invocation.output_tokens = output_tokens

                        # Cache token attributes (when provider exposes them)
                        # Check direct keys (Anthropic-style) and input_token_details (LangChain-style)
                        cache_read = (
                            chat_generation.message.usage_metadata.get(
                                "cache_read_input_tokens"
                            )
                        )
                        if cache_read is None:
                            input_token_details = (
                                chat_generation.message.usage_metadata.get(
                                    "input_token_details"
                                )
                            )
                            if isinstance(input_token_details, dict):
                                cache_read = input_token_details.get(
                                    "cache_read"
                                )
                        if cache_read is not None and llm_invocation.span:
                            llm_invocation.span.set_attribute(
                                "gen_ai.usage.cache_read.input_tokens",
                                int(cache_read),
                            )

                        cache_creation = (
                            chat_generation.message.usage_metadata.get(
                                "cache_creation_input_tokens"
                            )
                        )
                        if cache_creation is None:
                            input_token_details = (
                                chat_generation.message.usage_metadata.get(
                                    "input_token_details"
                                )
                            )
                            if isinstance(input_token_details, dict):
                                cache_creation = input_token_details.get(
                                    "cache_creation"
                                )
                        if cache_creation is not None and llm_invocation.span:
                            llm_invocation.span.set_attribute(
                                "gen_ai.usage.cache_creation.input_tokens",
                                int(cache_creation),
                            )

        llm_invocation.output_messages = output_messages

        llm_output = getattr(response, "llm_output", None)
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get(
                "model"
            )
            if response_model is not None:
                llm_invocation.response_model_name = str(response_model)

            response_id = llm_output.get("id")
            if response_id is not None:
                llm_invocation.response_id = str(response_id)

        # OpenAI-specific response attributes
        if llm_output is not None:
            system_fingerprint = llm_output.get("system_fingerprint")
            if system_fingerprint:
                if llm_invocation.span:
                    llm_invocation.span.set_attribute(
                        "openai.response.system_fingerprint",
                        str(system_fingerprint),
                    )

            service_tier = llm_output.get("service_tier")
            if service_tier:
                if llm_invocation.span:
                    llm_invocation.span.set_attribute(
                        "openai.response.service_tier",
                        str(service_tier),
                    )

        with self._streaming_lock:
            self._streaming_state.pop(str(run_id), None)

        llm_invocation = self._telemetry_handler.stop_llm(
            invocation=llm_invocation
        )

        # Propagate token usage to the nearest ancestor agent span.
        if self._span_manager and parent_run_id:
            self._span_manager.accumulate_llm_usage_to_agent(
                parent_run_id,
                llm_invocation.input_tokens,
                llm_invocation.output_tokens,
            )

        if llm_invocation.span and not llm_invocation.span.is_recording():
            self._invocation_manager.delete_invocation_state(run_id=run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        llm_invocation = self._invocation_manager.get_invocation(run_id=run_id)
        if llm_invocation is None or not isinstance(
            llm_invocation, LLMInvocation
        ):
            # If the invocation does not exist, we cannot set attributes or end it
            return

        error_otel = Error(message=str(error), type=type(error))
        with self._streaming_lock:
            self._streaming_state.pop(str(run_id), None)

        llm_invocation = self._telemetry_handler.fail_llm(
            invocation=llm_invocation, error=error_otel
        )
        if llm_invocation.span and not llm_invocation.span.is_recording():
            self._invocation_manager.delete_invocation_state(run_id=run_id)

    # ------------------------------------------------------------------
    # Chain callbacks (agent / workflow spans)
    # ------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        operation = classify_chain_run(
            serialized, metadata, kwargs, parent_run_id
        )
        if operation is None:
            self._span_manager.ignore_run(run_id, parent_run_id)
            return

        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: operation,
        }
        span_name = operation

        if operation == OperationName.INVOKE_AGENT:
            agent_name = resolve_agent_name(serialized, metadata, kwargs)
            if agent_name:
                attributes[GenAI.GEN_AI_AGENT_NAME] = agent_name
                span_name = f"{operation} {agent_name}"

            if metadata:
                agent_id = metadata.get("agent_id")
                if agent_id:
                    attributes[GenAI.GEN_AI_AGENT_ID] = str(agent_id)

                agent_desc = metadata.get("agent_description")
                if agent_desc:
                    attributes[GenAI.GEN_AI_AGENT_DESCRIPTION] = str(
                        agent_desc
                    )

                for key in ("thread_id", "session_id", "conversation_id"):
                    conv_id = metadata.get(key)
                    if conv_id:
                        attributes[GenAI.GEN_AI_CONVERSATION_ID] = str(conv_id)
                        break

            provider = infer_provider_name(serialized, metadata, None)
            if provider:
                attributes[GenAI.GEN_AI_PROVIDER_NAME] = provider
            elif metadata:
                provider_name = metadata.get("provider_name")
                if provider_name:
                    attributes[GenAI.GEN_AI_PROVIDER_NAME] = str(provider_name)

        elif operation == OperationName.INVOKE_WORKFLOW:
            workflow_name = kwargs.get("name") or serialized.get("name")
            if workflow_name:
                attributes[GEN_AI_WORKFLOW_NAME] = str(workflow_name)
                span_name = f"{operation} {workflow_name}"

        # Content recording (opt-in)
        policy = get_content_policy()
        formatted_input_messages = None
        system_instructions = None
        if policy.record_content:
            raw_messages = _extract_chain_messages(inputs)
            if raw_messages:
                formatted_input_messages, system_instructions = (
                    prepare_messages(
                        raw_messages,
                        record_content=True,
                    )
                )
        if policy.should_record_content_on_spans:
            if formatted_input_messages:
                attributes[GenAI.GEN_AI_INPUT_MESSAGES] = (
                    formatted_input_messages
                )
            if system_instructions:
                attributes[GenAI.GEN_AI_SYSTEM_INSTRUCTIONS] = (
                    system_instructions
                )

        headers = extract_propagation_context(metadata, inputs, kwargs)

        # Prefer the LangGraph logical thread_id from metadata; fall back
        # to the OS thread identifier for non-LangGraph chains.
        thread_key = (
            str(metadata["thread_id"])
            if metadata and metadata.get("thread_id")
            else str(threading.get_ident())
        )

        # For agent nodes, check for a goto-parent override produced by a
        # preceding LangGraph Command(goto=...) transition.
        effective_parent = parent_run_id
        if operation == OperationName.INVOKE_AGENT:
            goto_parent = self._span_manager.pop_goto_parent(thread_key)
            if goto_parent:
                effective_parent = goto_parent

        with propagated_context(headers):
            record = self._span_manager.start_span(
                run_id=run_id,
                name=span_name,
                operation=operation,
                parent_run_id=effective_parent,
                attributes=attributes,
                thread_key=thread_key,
            )

        if (
            self._event_emitter is not None
            and operation == OperationName.INVOKE_AGENT
        ):
            self._event_emitter.emit_agent_start_event(
                record.span,
                attributes.get(GenAI.GEN_AI_AGENT_NAME, span_name),
                formatted_input_messages,
            )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        if self._span_manager.is_ignored(run_id):
            self._span_manager.clear_ignored_run(run_id)
            return

        record = self._span_manager.get_record(run_id)
        if record is None:
            return

        policy = get_content_policy()
        formatted_output_messages = None
        if policy.record_content:
            raw_messages = _extract_chain_messages(outputs)
            if raw_messages:
                formatted_output_messages, _ = prepare_messages(
                    raw_messages,
                    record_content=True,
                )
        if policy.should_record_content_on_spans and formatted_output_messages:
            record.span.set_attribute(
                GenAI.GEN_AI_OUTPUT_MESSAGES, formatted_output_messages
            )
            record.attributes[GenAI.GEN_AI_OUTPUT_MESSAGES] = (
                formatted_output_messages
            )

        if (
            self._event_emitter is not None
            and record.operation == OperationName.INVOKE_AGENT
        ):
            self._event_emitter.emit_agent_end_event(
                record.span,
                record.attributes.get(
                    GenAI.GEN_AI_AGENT_NAME, record.operation
                ),
                formatted_output_messages,
            )

        # Detect LangGraph Command(goto=...) — the goto target should
        # become a child of this node's nearest agent ancestor.
        if _has_goto(outputs):
            thread_key = record.stash.get("thread_key")
            if thread_key:
                agent_parent = self._span_manager.nearest_agent_parent(record)
                if agent_parent:
                    self._span_manager.push_goto_parent(
                        thread_key, agent_parent
                    )

        self._span_manager.end_span(run_id, status=StatusCode.OK)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        if self._span_manager.is_ignored(run_id):
            self._span_manager.clear_ignored_run(run_id)
            return

        self._span_manager.end_span(run_id, error=error)

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager and parent_run_id:
            parent_key = self._span_manager.resolve_parent_id(parent_run_id)
            record = (
                self._span_manager.get_record(parent_key)
                if parent_key
                else None
            )
            if record:
                record.stash.setdefault("pending_actions", {})[str(run_id)] = {
                    "tool": action.tool,
                    "tool_input": action.tool_input,
                    "log": action.log,
                }

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if not self._span_manager:
            return
        record = self._span_manager.get_record(str(run_id))
        if not record:
            return
        if finish.return_values:
            record.span.set_attribute(
                GenAI.GEN_AI_OUTPUT_MESSAGES,
                json.dumps(finish.return_values, default=str),
            )
        record.span.set_status(Status(StatusCode.OK))
        self._span_manager.end_span(run_id)

    # ------------------------------------------------------------------
    # Tool callbacks
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        metadata = metadata or {}
        inputs = inputs or {}

        # Resolve tool name from multiple sources
        tool_name = (
            serialized.get("name")
            or metadata.get("tool_name")
            or kwargs.get("name")
            or "unknown_tool"
        )

        span_name = f"{OP_EXECUTE_TOOL} {tool_name}"

        # Build initial attributes
        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: OP_EXECUTE_TOOL,
            GenAI.GEN_AI_TOOL_NAME: tool_name,
        }

        # Tool description
        description = serialized.get("description")
        if description:
            attributes[GenAI.GEN_AI_TOOL_DESCRIPTION] = str(description)

        # Tool type: from serialized or infer from definition
        tool_type = serialized.get("type")
        if tool_type:
            attributes[GenAI.GEN_AI_TOOL_TYPE] = str(tool_type)

        # Tool call ID
        tool_call_id = inputs.get("tool_call_id") or metadata.get(
            "tool_call_id"
        )
        if tool_call_id:
            attributes[GenAI.GEN_AI_TOOL_CALL_ID] = str(tool_call_id)

        # Inherit provider from parent span if available
        resolved_parent_id = self._span_manager.resolve_parent_id(
            parent_run_id
        )
        if resolved_parent_id is not None:
            parent_record = self._span_manager.get_record(resolved_parent_id)
            if parent_record is not None:
                provider = parent_record.attributes.get(
                    GenAI.GEN_AI_PROVIDER_NAME
                )
                if provider:
                    attributes[GenAI.GEN_AI_PROVIDER_NAME] = provider

        # Tool call arguments (opt-in content)
        policy = get_content_policy()
        arguments = None
        if policy.record_content:
            if inputs:
                arg_data = {
                    k: v for k, v in inputs.items() if k != "tool_call_id"
                }
                if arg_data:
                    arguments = json.dumps(arg_data, default=str)
            if not arguments and input_str:
                arguments = input_str
        if should_record_tool_content(policy) and arguments:
            attributes[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS] = arguments

        # Thread key for agent stack tracking
        thread_key = metadata.get("thread_id")

        record = self._span_manager.start_span(
            run_id=str(run_id),
            name=span_name,
            operation=OP_EXECUTE_TOOL,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            attributes=attributes,
            thread_key=str(thread_key) if thread_key else None,
        )

        if self._event_emitter is not None:
            self._event_emitter.emit_tool_call_event(
                record.span,
                tool_name,
                arguments,
                str(tool_call_id) if tool_call_id else None,
            )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        record = self._span_manager.get_record(str(run_id))
        if record is None:
            return

        # Record tool result (opt-in content)
        policy = get_content_policy()
        result_str = None
        if policy.record_content and output is not None:
            result_str = serialize_tool_result(output, record_content=True)
        if should_record_tool_content(policy) and result_str is not None:
            record.span.set_attribute(
                GenAI.GEN_AI_TOOL_CALL_RESULT, result_str
            )
            record.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT] = result_str

        if self._event_emitter is not None:
            self._event_emitter.emit_tool_result_event(
                record.span,
                record.attributes.get(GenAI.GEN_AI_TOOL_NAME, "tool"),
                result_str,
                record.attributes.get(GenAI.GEN_AI_TOOL_CALL_ID),
            )

        # Detect LangGraph Command(goto=...) from tool output.
        if _has_goto(output):
            thread_key = record.stash.get("thread_key")
            if thread_key:
                agent_parent = self._span_manager.nearest_agent_parent(record)
                if agent_parent:
                    self._span_manager.push_goto_parent(
                        thread_key, agent_parent
                    )

        self._span_manager.end_span(run_id=str(run_id), status=StatusCode.OK)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        self._span_manager.end_span(run_id=str(run_id), error=error)

    # ------------------------------------------------------------------
    # Retriever callbacks
    # ------------------------------------------------------------------

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        metadata = metadata or {}

        tool_name = serialized.get("name", "retriever")
        span_name = f"{OP_EXECUTE_TOOL} {tool_name}"

        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: OP_EXECUTE_TOOL,
            GenAI.GEN_AI_TOOL_NAME: tool_name,
            GenAI.GEN_AI_TOOL_DESCRIPTION: serialized.get(
                "description", "retriever"
            ),
            GenAI.GEN_AI_TOOL_TYPE: "retriever",
        }

        # Inherit provider from parent span if available
        resolved_parent_id = self._span_manager.resolve_parent_id(
            parent_run_id
        )
        if resolved_parent_id is not None:
            parent_record = self._span_manager.get_record(resolved_parent_id)
            if parent_record is not None:
                provider = parent_record.attributes.get(
                    GenAI.GEN_AI_PROVIDER_NAME
                )
                if provider:
                    attributes[GenAI.GEN_AI_PROVIDER_NAME] = provider

        # Query text (opt-in content)
        policy = get_content_policy()
        if should_record_retriever_content(policy):
            attributes["gen_ai.retrieval.query.text"] = query

        thread_key = metadata.get("thread_id")

        record = self._span_manager.start_span(
            run_id=str(run_id),
            name=span_name,
            operation=OP_EXECUTE_TOOL,
            kind=SpanKind.INTERNAL,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            attributes=attributes,
            thread_key=str(thread_key) if thread_key else None,
        )

        if self._event_emitter is not None:
            self._event_emitter.emit_retriever_query_event(
                record.span,
                tool_name,
                query if policy.record_content else None,
            )

    def on_retriever_end(
        self,
        documents: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        record = self._span_manager.get_record(str(run_id))
        if record is None:
            return

        policy = get_content_policy()
        record_content = should_record_retriever_content(policy)
        formatted = format_documents(documents, record_content=record_content)
        if formatted is not None:
            record.span.set_attribute("gen_ai.retrieval.documents", formatted)
            record.attributes["gen_ai.retrieval.documents"] = formatted

        if self._event_emitter is not None:
            self._event_emitter.emit_retriever_result_event(
                record.span,
                record.attributes.get(GenAI.GEN_AI_TOOL_NAME, "retriever"),
                formatted,
            )

        self._span_manager.end_span(run_id=str(run_id), status=StatusCode.OK)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if self._span_manager is None:
            return

        self._span_manager.end_span(run_id=str(run_id), error=error)
