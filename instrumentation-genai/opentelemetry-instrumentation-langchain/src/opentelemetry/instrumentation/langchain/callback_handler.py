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

from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler  # type: ignore
from langchain_core.messages import BaseMessage  # type: ignore
from langchain_core.outputs import LLMResult  # type: ignore

from opentelemetry.instrumentation.langchain.invocation_manager import (
    _InvocationManager,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    def __init__(self, telemetry_handler: TelemetryHandler) -> None:
        super().__init__()  # type: ignore
        self._telemetry_handler = telemetry_handler
        self._invocation_manager = _InvocationManager()

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],  # type: ignore
        *,
        run_id: UUID,
        tags: list[str] | None,
        parent_run_id: UUID | None,
        metadata: dict[str, Any] | None,
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

        # TODO: uncomment and modify following after PR #3862 is merged
        # if params is not None:
        #     top_p = params.get("top_p")
        #     if top_p is not None:
        #         span.set_attribute(GenAI.GEN_AI_REQUEST_TOP_P, top_p)
        #     frequency_penalty = params.get("frequency_penalty")
        #     if frequency_penalty is not None:
        #         span.set_attribute(
        #             GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, frequency_penalty
        #         )
        #     presence_penalty = params.get("presence_penalty")
        #     if presence_penalty is not None:
        #         span.set_attribute(
        #             GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, presence_penalty
        #         )
        #     stop_sequences = params.get("stop")
        #     if stop_sequences is not None:
        #         span.set_attribute(
        #             GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, stop_sequences
        #         )
        #     seed = params.get("seed")
        #     if seed is not None:
        #         span.set_attribute(GenAI.GEN_AI_REQUEST_SEED, seed)
        #     # ChatOpenAI
        #     temperature = params.get("temperature")
        #     if temperature is not None:
        #         span.set_attribute(
        #             GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
        #         )
        #     # ChatOpenAI
        #     max_tokens = params.get("max_completion_tokens")
        #     if max_tokens is not None:
        #         span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)
        #
        provider = "unknown"
        if metadata is not None:
            provider = metadata.get("ls_provider")

        # TODO: uncomment and modify following after PR #3862 is merged

        #     # ChatBedrock
        #     temperature = metadata.get("ls_temperature")
        #     if temperature is not None:
        #         span.set_attribute(
        #             GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
        #         )
        #     # ChatBedrock
        #     max_tokens = metadata.get("ls_max_tokens")
        #     if max_tokens is not None:
        #         span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)

        input_messages: list[InputMessage] = []
        for sub_messages in messages:  # type: ignore[reportUnknownVariableType]
            for message in sub_messages:  # type: ignore[reportUnknownVariableType]
                content = get_property_value(message, "content")  # type: ignore[reportUnknownVariableType]
                role = get_property_value(message, "type")  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]
                parts = [Text(content=content, type="text")]  # type: ignore[reportArgumentType]
                input_messages.append(InputMessage(parts=parts, role=role))  # type: ignore[reportArgumentType]

        llm_invocation = LLMInvocation(
            request_model=request_model,
            input_messages=input_messages,
            provider=provider,
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
        response: LLMResult,  # type: ignore [reportUnknownParameterType]
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        **kwargs: Any,
    ) -> None:
        invocation = self._invocation_manager.get_invocation(run_id=run_id)

        if invocation is None or not isinstance(invocation, LLMInvocation):
            # If the invocation does not exist, we cannot set attributes or end it
            return

        llm_invocation: LLMInvocation = invocation

        output_messages: list[OutputMessage] = []
        for generation in getattr(response, "generations", []):  # type: ignore
            for chat_generation in generation:
                # Get finish reason
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
                            content=get_property_value(  # type: ignore[reportArgumentType]
                                chat_generation.message, "content"
                            ),
                            type="text",
                        )
                    ]
                    role = get_property_value(chat_generation.message, "type")  # type: ignore[reportUnknownVariableType]
                    output_message = OutputMessage(
                        role=role, # type: ignore[reportArgumentType]
                        parts=parts,
                        finish_reason=finish_reason,  # type: ignore[reportPossiblyUnboundVariable, reportArgumentType]
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

        llm_output = getattr(response, "llm_output", None)  # type: ignore
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get(
                "model"
            )
            if response_model is not None:
                llm_invocation.response_model_name = str(response_model)

            response_id = llm_output.get("id")
            if response_id is not None:
                llm_invocation.response_id = str(response_id)

        invocation = self._telemetry_handler.stop_llm(invocation=invocation)
        if not invocation.span.is_recording():  # type: ignore[reportOptionalMemberAccess]
            self._invocation_manager.delete_invocation_state(run_id=run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        **kwargs: Any,
    ) -> None:
        invocation = self._invocation_manager.get_invocation(run_id=run_id)  # type: ignore[reportAssignmentType]

        if invocation is None or not isinstance(invocation, LLMInvocation):  # type: ignore[reportUnnecessaryIsInstance, reportUnnecessaryComparison]
            # If the invocation does not exist, we cannot set attributes or end it
            return

        invocation: LLMInvocation = invocation

        error = Error(message=str(error), type=type(error))  # type: ignore[reportAssignmentType]
        invocation = self._telemetry_handler.fail_llm(
            invocation=invocation,
            error=error,  # type: ignore[reportArgumentType]
        )
        if not invocation.span.is_recording():  # type: ignore[reportOptionalMemberAccess]
            self._invocation_manager.delete_invocation_state(run_id=run_id)


def get_property_value(obj, property_name):  # type: ignore[reportUnknownParameterType]
    if isinstance(obj, dict):
        return obj.get(property_name, None)  # type: ignore[reportUnknownArgumentType]

    return getattr(obj, property_name, None)  # type: ignore[reportUnknownArgumentType]
