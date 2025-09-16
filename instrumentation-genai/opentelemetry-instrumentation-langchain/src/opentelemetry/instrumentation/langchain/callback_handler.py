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

import logging
from typing import List, Optional, Union, Any, Dict
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.utils import dont_throw
from .utils import get_property_value
from opentelemetry.genai.sdk.data import (
    Message,
    ChatGeneration,
    Error,
    ToolOutput, ToolFunction, ToolFunctionCall
)
from .utils import should_enable_evaluation
from opentelemetry.genai.sdk.api import TelemetryClient
from opentelemetry.genai.sdk.evals import Evaluator
from opentelemetry.genai.sdk.types import LLMInvocation

logger = logging.getLogger(__name__)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans
    for chains, LLM calls, and tools.
    """

    def __init__(
        self,
        telemetry_client: TelemetryClient,
        evaluation_client: Evaluator,
    ) -> None:
        super().__init__()
        self._telemetry_client = telemetry_client
        self._evaluation_client = evaluation_client

    @dont_throw
    def on_chat_model_start(
        self,
        serialized: dict,
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        tags: Optional[List[str]] = None,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        system = serialized.get("name", kwargs.get("name", "ChatLLM"))
        invocation_params =  kwargs.get("invocation_params", {})

        attributes = {
            "system": system,
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "framework": "langchain",
        }

        if invocation_params:
            request_model = invocation_params.get("model_name")
            if request_model:
                attributes.update({"request_model": request_model})
            top_p = invocation_params.get("top_p")
            if top_p:
                attributes.update({"request_top_p": top_p})
            frequency_penalty = invocation_params.get("frequency_penalty")
            if frequency_penalty:
                attributes.update({"request_frequency_penalty": frequency_penalty})
            presence_penalty = invocation_params.get("presence_penalty")
            if presence_penalty:
                attributes.update({"request_presence_penalty": presence_penalty})
            stop_sequences = invocation_params.get("stop")
            if stop_sequences:
                attributes.update({"request_stop_sequences": stop_sequences})
            seed = invocation_params.get("seed")
            if seed:
                attributes.update({"request_seed": seed})

        if metadata:
            max_tokens = metadata.get("ls_max_tokens")
            if max_tokens:
                attributes.update({"request_max_tokens": max_tokens})
            provider_name = metadata.get("ls_provider")
            if provider_name:
                # TODO: add to semantic conventions
                attributes.update({"provider_name": provider_name})
            temperature = metadata.get("ls_temperature")
            if temperature:
                attributes.update({"request_temperature": temperature})

        # invoked during first invoke to llm with tool start --
        tool_functions: List[ToolFunction] = []
        tools = kwargs.get("invocation_params").get("tools") if kwargs.get("invocation_params") else None
        if tools is not None:
            for index, tool in enumerate(tools):
                function = tool.get("function")
                if function is not None:
                    tool_function = ToolFunction(
                        name=function.get("name"),
                        description=function.get("description"),
                        parameters=str(function.get("parameters"))
                    )
                    tool_functions.append(tool_function)
        # tool end --


        prompts: list[Message] = []
        for sub_messages in messages:
            for message in sub_messages:
                # llm invoked with  all messages tool support start --
                additional_kwargs = get_property_value(message, "additional_kwargs")
                tool_calls = get_property_value(additional_kwargs, "tool_calls")
                tool_function_calls = []
                for tool_call in tool_calls or []:
                    tool_function_call = ToolFunctionCall(
                        id=tool_call.get("id"),
                        name=tool_call.get("function").get("name"),
                        arguments=str(tool_call.get("function").get("arguments")),
                        type=tool_call.get("type"),
                    )
                    tool_function_calls.append(tool_function_call)
                # tool support end --
                prompt = Message(
                    name=get_property_value(message, "name"),
                    content=get_property_value(message, "content"),
                    type=get_property_value(message, "type"),
                    tool_call_id=get_property_value(message, "tool_call_id"),
                    tool_function_calls=tool_function_calls,
                )
                prompts.append(prompt)

        # Invoke genai-sdk api
        self._telemetry_client.start_llm(prompts, tool_functions, run_id, parent_run_id, **attributes)

    @dont_throw
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Union[UUID, None] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        chat_generations: list[ChatGeneration] = []
        tool_function_calls: list[ToolFunctionCall] = []
        for generation in getattr(response, "generations", []):
            for chat_generation in generation:
                # llm creates tool calls during first llm invoke tool support start --
                tool_calls = chat_generation.message.additional_kwargs.get("tool_calls")
                for tool_call in tool_calls or []:
                    tool_function_call = ToolFunctionCall(
                        id=tool_call.get("id"),
                        name=tool_call.get("function").get("name"),
                        arguments=tool_call.get("function").get("arguments"),
                        type=tool_call.get("type"),
                    )
                    tool_function_calls.append(tool_function_call)
                # tool support end --
                if chat_generation.generation_info is not None:
                    finish_reason = chat_generation.generation_info.get("finish_reason")
                    content = get_property_value(chat_generation.message, "content")
                    chat = ChatGeneration(
                        content=content,
                        type=chat_generation.type,
                        finish_reason=finish_reason,
                        tool_function_calls=tool_function_calls,
                    )
                    chat_generations.append(chat)

        response_model = response_id = None
        llm_output = response.llm_output
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get("model")
            response_id = llm_output.get("id")

        input_tokens = output_tokens = None
        usage = response.llm_output.get("usage") or response.llm_output.get("token_usage")
        if usage:
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

        attributes = {
            "response_model_name": response_model,
            "response_id": response_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        # Invoke genai-sdk api
        invocation: LLMInvocation =  self._telemetry_client.stop_llm(run_id=run_id, chat_generations=chat_generations, **attributes)

        # generates evaluation child spans.
        # pass only required attributes to evaluation client
        if should_enable_evaluation():
            import asyncio
            asyncio.create_task(self._evaluation_client.evaluate(invocation))
        # self._evaluation_client.evaluate(invocation)


    @dont_throw
    def on_tool_start(
        self,
        serialized: dict,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        tool_name = serialized.get("name") or kwargs.get("name") or "execute_tool"
        attributes = {
            "tool_name": tool_name,
            "description": serialized.get("description"),
        }

        # Invoke genai-sdk api
        self._telemetry_client.start_tool(run_id=run_id, input_str=input_str, **attributes)

    @dont_throw
    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        output = ToolOutput(
            content=get_property_value(output, "content"),
            tool_call_id=get_property_value(output, "tool_call_id"),
        )
        # Invoke genai-sdk api
        self._telemetry_client.stop_tool(run_id=run_id, output=output)

    @dont_throw
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        llm_error = Error(message=str(error), type=type(error))
        self._telemetry_client.fail_llm(run_id=run_id, error=llm_error, **kwargs)

    @dont_throw
    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        tool_error = Error(message=str(error), type=type(error))
        self._telemetry_client.fail_tool(run_id=run_id, error=tool_error, **kwargs)