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
from threading import Lock
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.utils import dont_throw
from opentelemetry.util.genai.handler import (
    get_telemetry_handler as _get_util_handler,
)
from opentelemetry.util.genai.types import (
    Error as UtilError,
)
from opentelemetry.util.genai.types import (
    InputMessage as UtilInputMessage,
)
from opentelemetry.util.genai.types import (
    LLMInvocation as UtilLLMInvocation,
)
from opentelemetry.util.genai.types import (
    OutputMessage as UtilOutputMessage,
)
from opentelemetry.util.genai.types import (
    Text as UtilText,
)

from .utils import get_property_value

logger = logging.getLogger(__name__)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler using opentelemetry-util-genai only (legacy genai-sdk removed)."""

    def __init__(self):
        super().__init__()
        self._telemetry_handler = _get_util_handler()
        self._invocations: dict[UUID, UtilLLMInvocation] = {}
        self._lock = Lock()

    def _build_input_messages(
        self, messages: List[List[BaseMessage]]
    ) -> list[UtilInputMessage]:
        result: list[UtilInputMessage] = []
        for sub in messages:
            for m in sub:
                role = (
                    getattr(m, "type", None)
                    or m.__class__.__name__.replace("Message", "").lower()
                )
                content = get_property_value(m, "content")
                result.append(
                    UtilInputMessage(
                        role=role, parts=[UtilText(content=str(content))]
                    )
                )
        return result

    def _add_tool_definition_attrs(self, invocation_params: dict, attrs: dict):
        tools = invocation_params.get("tools") if invocation_params else None
        if not tools:
            return
        for idx, tool in enumerate(tools):
            fn = tool.get("function") if isinstance(tool, dict) else None
            if not fn:
                continue
            name = fn.get("name")
            desc = fn.get("description")
            params = fn.get("parameters")
            if name:
                attrs[f"gen_ai.request.function.{idx}.name"] = name
            if desc:
                attrs[f"gen_ai.request.function.{idx}.description"] = desc
            if params is not None:
                attrs[f"gen_ai.request.function.{idx}.parameters"] = str(
                    params
                )

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
        invocation_params = kwargs.get("invocation_params") or {}
        request_model = (
            invocation_params.get("model_name")
            or serialized.get("name")
            or "unknown-model"
        )
        provider_name = (metadata or {}).get("ls_provider")
        attrs: dict[str, Any] = {"framework": "langchain"}
        # copy selected params
        for key in (
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "seed",
        ):
            if key in invocation_params and invocation_params[key] is not None:
                attrs[f"request_{key}"] = invocation_params[key]
        if metadata:
            if metadata.get("ls_max_tokens") is not None:
                attrs["request_max_tokens"] = metadata.get("ls_max_tokens")
            if metadata.get("ls_temperature") is not None:
                attrs["request_temperature"] = metadata.get("ls_temperature")
        self._add_tool_definition_attrs(invocation_params, attrs)
        input_messages = self._build_input_messages(messages)
        inv = UtilLLMInvocation(
            request_model=request_model,
            provider=provider_name,
            input_messages=input_messages,
            attributes=attrs,
        )
        self._telemetry_handler.start_llm(inv)
        with self._lock:
            self._invocations[run_id] = inv

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
        with self._lock:
            inv = self._invocations.pop(run_id, None)
        if not inv:
            return
        generations = getattr(response, "generations", [])
        content_text = None
        finish_reason = "stop"
        if generations:
            first_list = generations[0]
            if first_list:
                first = first_list[0]
                content_text = get_property_value(first.message, "content")
                if getattr(first, "generation_info", None):
                    finish_reason = first.generation_info.get(
                        "finish_reason", finish_reason
                    )
        if content_text is not None:
            inv.output_messages = [
                UtilOutputMessage(
                    role="assistant",
                    parts=[UtilText(content=str(content_text))],
                    finish_reason=finish_reason,
                )
            ]
        llm_output = getattr(response, "llm_output", None) or {}
        response_model = llm_output.get("model_name") or llm_output.get(
            "model"
        )
        response_id = llm_output.get("id")
        usage = llm_output.get("usage") or llm_output.get("token_usage") or {}
        inv.response_model_name = response_model
        inv.response_id = response_id
        if usage:
            inv.input_tokens = usage.get("prompt_tokens")
            inv.output_tokens = usage.get("completion_tokens")
        self._telemetry_handler.stop_llm(inv)
        try:
            self._telemetry_handler.evaluate_llm(inv)
        except Exception:  # pragma: no cover
            pass

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
        with self._lock:
            inv = self._invocations.pop(run_id, None)
        if not inv:
            return
        self._telemetry_handler.fail_llm(
            inv, UtilError(message=str(error), type=type(error))
        )

    # Tool callbacks currently no-op (tool definitions captured on start)
    @dont_throw
    def on_tool_start(self, *args, **kwargs):
        return

    @dont_throw
    def on_tool_end(self, *args, **kwargs):
        return

    @dont_throw
    def on_tool_error(self, *args, **kwargs):
        return
