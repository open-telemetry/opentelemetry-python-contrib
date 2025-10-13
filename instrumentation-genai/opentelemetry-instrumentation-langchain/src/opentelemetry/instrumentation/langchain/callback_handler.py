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

from langchain_core.agents import AgentAction, AgentFinish  # type: ignore
from langchain_core.callbacks import BaseCallbackHandler  # type: ignore
from langchain_core.messages import BaseMessage  # type: ignore
from langchain_core.outputs import LLMResult  # type: ignore

from opentelemetry.instrumentation.langchain.span_manager import (
    _OPERATION_INVOKE_AGENT,
    _SpanManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import Tracer


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    def __init__(
        self,
        tracer: Tracer,
    ) -> None:
        super().__init__()  # type: ignore

        self.span_manager = _SpanManager(
            tracer=tracer,
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],  # type: ignore
        *,
        run_id: UUID,
        tags: list[str] | None = None,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
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

        span = self.span_manager.create_chat_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            request_model=request_model,
        )

        if params is not None:
            top_p = params.get("top_p")
            if top_p is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_TOP_P, top_p)
            frequency_penalty = params.get("frequency_penalty")
            if frequency_penalty is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, frequency_penalty
                )
            presence_penalty = params.get("presence_penalty")
            if presence_penalty is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, presence_penalty
                )
            stop_sequences = params.get("stop")
            if stop_sequences is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, stop_sequences
                )
            seed = params.get("seed")
            if seed is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_SEED, seed)
            # ChatOpenAI
            temperature = params.get("temperature")
            if temperature is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
                )
            # ChatOpenAI
            max_tokens = params.get("max_completion_tokens")
            if max_tokens is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)

        if metadata is not None:
            provider = metadata.get("ls_provider")
            if provider is not None:
                span.set_attribute("gen_ai.provider.name", provider)
            # ChatBedrock
            temperature = metadata.get("ls_temperature")
            if temperature is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
                )
            # ChatBedrock
            max_tokens = metadata.get("ls_max_tokens")
            if max_tokens is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)

    def on_llm_end(
        self,
        response: LLMResult,  # type: ignore [reportUnknownParameterType]
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        span = self.span_manager.get_span(run_id)

        if span is None:
            # If the span does not exist, we cannot set attributes or end it
            return

        finish_reasons: list[str] = []
        for generation in getattr(response, "generations", []):  # type: ignore
            for chat_generation in generation:
                generation_info = getattr(
                    chat_generation, "generation_info", None
                )
                if generation_info is not None:
                    finish_reason = generation_info.get(
                        "finish_reason", "unknown"
                    )
                    if finish_reason is not None:
                        finish_reasons.append(str(finish_reason))
                if chat_generation.message:
                    if (
                        generation_info is None
                        and chat_generation.message.response_metadata
                    ):
                        finish_reason = (
                            chat_generation.message.response_metadata.get(
                                "stopReason", "unknown"
                            )
                        )
                        if finish_reason is not None:
                            finish_reasons.append(str(finish_reason))
                    if chat_generation.message.usage_metadata:
                        input_tokens = (
                            chat_generation.message.usage_metadata.get(
                                "input_tokens", 0
                            )
                        )
                        output_tokens = (
                            chat_generation.message.usage_metadata.get(
                                "output_tokens", 0
                            )
                        )
                        span.set_attribute(
                            GenAI.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
                        )
                        span.set_attribute(
                            GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
                        )

        span.set_attribute(
            GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
        )

        llm_output = getattr(response, "llm_output", None)  # type: ignore
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get(
                "model"
            )
            if response_model is not None:
                span.set_attribute(
                    GenAI.GEN_AI_RESPONSE_MODEL, str(response_model)
                )

            response_id = llm_output.get("id")
            if response_id is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, str(response_id))

        # End the LLM span
        self.span_manager.end_span(run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self.span_manager.handle_error(error, run_id)

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain starts running."""
        # Extract chain name from serialized or kwargs
        chain_name = "unknown"
        if (
            serialized
            and "kwargs" in serialized
            and serialized["kwargs"].get("name")
        ):
            chain_name = serialized["kwargs"]["name"]
        elif kwargs.get("name"):
            chain_name = kwargs["name"]
        elif serialized.get("name"):
            chain_name = serialized["name"]
        elif "id" in serialized:
            chain_name = serialized["id"][-1]

        span = self.span_manager.create_chain_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            chain_name=chain_name,
        )

        # If this is an agent chain, set agent-specific attributes
        if metadata and "agent_name" in metadata:
            span.set_attribute(GenAI.GEN_AI_AGENT_NAME, metadata["agent_name"])
            span.set_attribute(
                GenAI.GEN_AI_OPERATION_NAME, _OPERATION_INVOKE_AGENT
            )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain ends running."""
        self.span_manager.end_span(run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain errors."""
        self.span_manager.handle_error(error, run_id)

    def on_agent_action(
        self,
        action: AgentAction,  # type: ignore[type-arg]
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run on agent action."""
        # Agent actions are tracked as part of the chain span
        # We can add attributes to the existing span if needed
        span = self.span_manager.get_span(run_id)
        if span:
            tool = getattr(action, "tool", None)  # type: ignore[arg-type]
            if tool:
                span.set_attribute("langchain.agent.action.tool", tool)
            tool_input = getattr(action, "tool_input", None)  # type: ignore[arg-type]
            if tool_input:
                span.set_attribute(
                    "langchain.agent.action.tool_input", str(tool_input)
                )

    def on_agent_finish(
        self,
        finish: AgentFinish,  # type: ignore[type-arg]
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Run on agent finish."""
        # Agent finish is tracked as part of the chain span
        span = self.span_manager.get_span(run_id)
        if span:
            return_values = getattr(finish, "return_values", None)  # type: ignore[arg-type]
            if return_values and "output" in return_values:
                span.set_attribute(
                    "langchain.agent.finish.output",
                    str(return_values["output"]),
                )
