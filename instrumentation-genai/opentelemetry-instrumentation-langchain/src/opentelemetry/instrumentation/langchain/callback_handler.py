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
from typing import List, Optional, Union
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
)
from opentelemetry.genai.sdk.api import TelemetryClient

logger = logging.getLogger(__name__)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans
    for chains, LLM calls, and tools.
    """

    def __init__(
        self,
        telemetry_client: TelemetryClient,
    ) -> None:
        super().__init__()
        self._telemetry_client = telemetry_client
        self.run_inline = True  # Whether to run the callback inline.

    @dont_throw
    def on_chat_model_start(
        self,
        serialized: dict,
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        request_model = kwargs.get("invocation_params", {}).get("model_name")
        system = serialized.get("name", kwargs.get("name", "ChatLLM"))
        attributes = {
            "request_model": request_model,
            "system": system,
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "framework": "langchain",
        }

        prompts: list[Message] = [
            Message(
                content=get_property_value(message, "content"),
                type=get_property_value(message, "type"),
            )
            for sub_messages in messages
            for message in sub_messages
        ]

        # Invoke genai-sdk api
        self._telemetry_client.start_llm(prompts, run_id, parent_run_id, **attributes)

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
        for generation in getattr(response, "generations", []):
            for chat_generation in generation:
                if chat_generation.generation_info is not None:
                    finish_reason = chat_generation.generation_info.get("finish_reason")
                    content = get_property_value(chat_generation.message, "content")
                    chat = ChatGeneration(
                        content=content,
                        type=chat_generation.type,
                        finish_reason=finish_reason,
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
        self._telemetry_client.stop_llm(run_id=run_id, chat_generations=chat_generations, **attributes)

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