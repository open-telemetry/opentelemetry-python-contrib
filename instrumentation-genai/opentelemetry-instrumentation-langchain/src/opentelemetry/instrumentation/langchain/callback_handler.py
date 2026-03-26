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

from typing import Any, Optional, Sequence
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from opentelemetry.instrumentation.langchain.invocation_manager import (
    _InvocationManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)
from opentelemetry.util.genai.utils import (
    get_content_capturing_mode,
    is_experimental_mode,
)

GEN_AI_MEMORY_STORE_ID = getattr(
    GenAI, "GEN_AI_MEMORY_STORE_ID", "gen_ai.memory.store.id"
)
GEN_AI_MEMORY_STORE_NAME = getattr(
    GenAI, "GEN_AI_MEMORY_STORE_NAME", "gen_ai.memory.store.name"
)
GEN_AI_MEMORY_QUERY = getattr(
    GenAI, "GEN_AI_MEMORY_QUERY", "gen_ai.memory.query"
)
GEN_AI_MEMORY_SEARCH_RESULT_COUNT = getattr(
    GenAI,
    "GEN_AI_MEMORY_SEARCH_RESULT_COUNT",
    "gen_ai.memory.search.result.count",
)
GEN_AI_MEMORY_NAMESPACE = getattr(
    GenAI, "GEN_AI_MEMORY_NAMESPACE", "gen_ai.memory.namespace"
)

_SEARCH_MEMORY_MEMBER = getattr(
    getattr(GenAI, "GenAiOperationNameValues", object()),
    "SEARCH_MEMORY",
    None,
)
SEARCH_MEMORY_OPERATION = (
    _SEARCH_MEMORY_MEMBER.value
    if _SEARCH_MEMORY_MEMBER is not None
    else "search_memory"
)

_RETRIEVAL_MEMBER = getattr(
    getattr(GenAI, "GenAiOperationNameValues", object()),
    "RETRIEVAL",
    None,
)
RETRIEVAL_OPERATION = (
    _RETRIEVAL_MEMBER.value if _RETRIEVAL_MEMBER is not None else "retrieval"
)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    def __init__(self, telemetry_handler: TelemetryHandler) -> None:
        super().__init__()
        self._telemetry_handler = telemetry_handler
        self._invocation_manager = _InvocationManager()

    @staticmethod
    def _resolve_retriever_store_name(
        serialized: dict[str, Any],
        metadata: Optional[dict[str, Any]],
    ) -> Optional[str]:
        if metadata and metadata.get("memory_store_name"):
            return str(metadata["memory_store_name"])
        if metadata and metadata.get("ls_retriever_name"):
            return str(metadata["ls_retriever_name"])
        name = serialized.get("name")
        return str(name) if isinstance(name, str) and name else None

    @staticmethod
    def _resolve_retriever_store_id(
        serialized: dict[str, Any],
        metadata: Optional[dict[str, Any]],
    ) -> Optional[str]:
        if metadata and metadata.get("memory_store_id"):
            return str(metadata["memory_store_id"])

        serialized_id = serialized.get("id")
        if isinstance(serialized_id, str) and serialized_id:
            return serialized_id
        if isinstance(serialized_id, list) and serialized_id:
            try:
                return ".".join(str(part) for part in serialized_id)  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            except TypeError:
                return None
        return None

    @staticmethod
    def _should_capture_memory_query() -> bool:
        if not is_experimental_mode():
            return False
        try:
            mode = get_content_capturing_mode()
        except ValueError:
            return False
        return mode in (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )

    @staticmethod
    def _is_memory_retriever(
        metadata: Optional[dict[str, Any]],
    ) -> bool:
        """Detect if a retriever is a memory retriever based on metadata hints."""
        if not metadata:
            return False
        return bool(
            metadata.get("memory_store_name")
            or metadata.get("memory_store_id")
            or metadata.get("is_memory_retriever")
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
        # Other providers/LLMs may be supported in the future and telemetry for them is skipped for now.
        if serialized.get("name") not in ("ChatOpenAI", "ChatBedrock"):
            return

        if "invocation_params" in kwargs:
            params = (
                kwargs["invocation_params"].get("params")
                or kwargs["invocation_params"]
            )
        else:
            params = kwargs

        request_model = "unknown"
        for model_tag in (
            "model_name",  # ChatOpenAI
            "model_id",  # ChatBedrock
        ):
            if (model := (params or {}).get(model_tag)) is not None:
                request_model = model
                break
            elif (model := (metadata or {}).get(model_tag)) is not None:
                request_model = model
                break

        # Skip telemetry for unsupported request models
        if request_model == "unknown":
            return

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

        provider = "unknown"
        if metadata is not None:
            provider = metadata.get("ls_provider", "unknown")

            # Override with ChatBedrock values if present
            if "ls_temperature" in metadata:
                temperature = metadata.get("ls_temperature")
            if "ls_max_tokens" in metadata:
                max_tokens = metadata.get("ls_max_tokens")

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

                input_messages.append(InputMessage(parts=parts, role=role))

        llm_invocation = LLMInvocation(
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
        )
        llm_invocation = self._telemetry_handler.start_llm(
            invocation=llm_invocation
        )
        self._invocation_manager.add_invocation_state(
            run_id=run_id,
            parent_run_id=parent_run_id,
            invocation=llm_invocation,
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
                        parts=parts,
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

        llm_invocation = self._telemetry_handler.stop_llm(
            invocation=llm_invocation
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
        llm_invocation = self._telemetry_handler.fail_llm(
            invocation=llm_invocation, error=error_otel
        )
        if llm_invocation.span and not llm_invocation.span.is_recording():
            self._invocation_manager.delete_invocation_state(run_id=run_id)

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
        provider = "unknown"
        if metadata is not None:
            provider = metadata.get("ls_provider", "unknown")

        attributes: dict[str, Any] = {}
        is_memory = self._is_memory_retriever(metadata)
        operation = (
            SEARCH_MEMORY_OPERATION if is_memory else RETRIEVAL_OPERATION
        )

        if store_name := self._resolve_retriever_store_name(
            serialized, metadata
        ):
            attributes[GEN_AI_MEMORY_STORE_NAME] = store_name
        if store_id := self._resolve_retriever_store_id(serialized, metadata):
            attributes[GEN_AI_MEMORY_STORE_ID] = store_id
        if query and self._should_capture_memory_query():
            attributes[GEN_AI_MEMORY_QUERY] = query
        if metadata and metadata.get("memory_namespace"):
            attributes[GEN_AI_MEMORY_NAMESPACE] = metadata["memory_namespace"]

        llm_invocation = LLMInvocation(
            request_model="",
            provider=provider,
            operation_name=operation,
            attributes=attributes,
        )
        llm_invocation = self._telemetry_handler.start_llm(
            invocation=llm_invocation
        )
        if llm_invocation.span and store_name:
            llm_invocation.span.update_name(f"{operation} {store_name}")
        self._invocation_manager.add_invocation_state(
            run_id=run_id,
            parent_run_id=parent_run_id,
            invocation=llm_invocation,
        )

    def on_retriever_end(
        self,
        documents: Sequence[Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        llm_invocation = self._invocation_manager.get_invocation(run_id=run_id)
        if llm_invocation is None or not isinstance(
            llm_invocation, LLMInvocation
        ):
            return

        llm_invocation.attributes[GEN_AI_MEMORY_SEARCH_RESULT_COUNT] = len(
            documents
        )
        llm_invocation = self._telemetry_handler.stop_llm(
            invocation=llm_invocation
        )
        if llm_invocation.span and not llm_invocation.span.is_recording():
            self._invocation_manager.delete_invocation_state(run_id=run_id)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        llm_invocation = self._invocation_manager.get_invocation(run_id=run_id)
        if llm_invocation is None or not isinstance(
            llm_invocation, LLMInvocation
        ):
            return

        error_otel = Error(message=str(error), type=type(error))
        llm_invocation = self._telemetry_handler.fail_llm(
            invocation=llm_invocation, error=error_otel
        )
        if llm_invocation.span and not llm_invocation.span.is_recording():
            self._invocation_manager.delete_invocation_state(run_id=run_id)
