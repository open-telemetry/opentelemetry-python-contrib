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

"""
Langchain instrumentation supporting `ChatOpenAI`, it can be enabled by
using ``LangChainInstrumentor``.

.. _langchain: https://pypi.org/project/langchain/

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.langchain import LangChainInstrumentor
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    LangChainInstrumentor().instrument()

    llm = ChatOpenAI(model="gpt-3.5-turbo")
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = llm.invoke(messages)

API
---
"""

import json
import os
from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttr,
)
from opentelemetry.util.genai.handler import TelemetryHandler
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
from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
# from opentelemetry.instrumentation.langchain.version import __version__


class LangChainInstrumentor(BaseInstrumentor):
    """
    OpenTelemetry instrumentor for LangChain.

    This adds a custom callback handler to the LangChain callback manager
    to capture chain, LLM, and tool events. It also wraps the internal
    OpenAI invocation points (BaseChatOpenAI) to inject W3C trace headers
    for downstream calls to OpenAI (or other providers).
    """

    def __init__(
        self, exception_logger=None, disable_trace_injection: bool = False
    ):
        """
        :param disable_trace_injection: If True, do not wrap OpenAI invocation
                                        for trace-context injection.
        """
        super().__init__()
        self._disable_trace_injection = disable_trace_injection
        Config.exception_logger = exception_logger

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        # Ensure metrics + events generator by default
        from opentelemetry.util.genai.environment_variables import OTEL_INSTRUMENTATION_GENAI_EMITTERS

        if not os.environ.get(OTEL_INSTRUMENTATION_GENAI_EMITTERS):
            os.environ[OTEL_INSTRUMENTATION_GENAI_EMITTERS] = "span_metric_event"
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")
        # Create dedicated handler bound to provided tracer and meter providers (ensures spans and metrics go to test exporters)
        self._telemetry_handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )
        otel_callback_handler = OpenTelemetryLangChainCallbackHandler()

        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(otel_callback_handler),
        )

        def _build_input_messages(messages):
            result = []
            if not messages:
                return result
            # messages can be list[BaseMessage] or list[list[BaseMessage]]
            if messages and isinstance(messages[0], list):
                outer = messages
            else:
                outer = [messages]
            for sub in outer:
                for m in sub:
                    role = (
                        getattr(m, "type", None)
                        or m.__class__.__name__.replace("Message", "").lower()
                    )
                    content = getattr(m, "content", None)
                    result.append(
                        UtilInputMessage(
                            role=role, parts=[UtilText(content=str(content))]
                        )
                    )
            return result

        def _extract_generation_data(response):
            content_text = None
            finish_reason = "stop"
            try:
                gens = getattr(response, "generations", [])
                if gens and gens[0]:
                    first = gens[0][0]
                    # newer LangChain message content
                    if hasattr(first, "message") and hasattr(
                        first.message, "content"
                    ):
                        content_text = first.message.content
                    elif hasattr(first, "text"):
                        content_text = first.text
                    gen_info = getattr(first, "generation_info", None)
                    if gen_info and isinstance(gen_info, dict):
                        finish_reason = gen_info.get(
                            "finish_reason", finish_reason
                        )
            except Exception:
                pass
            usage = getattr(response, "llm_output", None) or {}
            return content_text, finish_reason, usage

        def _apply_usage(inv, usage):
            if not usage or not isinstance(usage, dict):
                return
            token_usage = (
                usage.get("token_usage") or usage.get("usage") or usage
            )
            if isinstance(token_usage, dict):
                inv.input_tokens = token_usage.get("prompt_tokens")
                inv.output_tokens = token_usage.get("completion_tokens")

        def _start_invocation(instance, messages, invocation_params):
            # Enhanced model detection
            request_model = (
                invocation_params.get("model_name")
                or invocation_params.get("model")
                or getattr(instance, "model_name", None)
                or getattr(instance, "model", None)
                or getattr(instance, "_model", None)
            )
            if not request_model:
                # heuristic scan of instance __dict__
                for k, v in getattr(instance, "__dict__", {}).items():
                    if isinstance(v, str) and (
                        "model" in k.lower()
                        or v.startswith("gpt-")
                        or v.endswith("-mini")
                    ):
                        request_model = v
                        break
            request_model = request_model or "unknown-model"
            attrs = {"framework": "langchain"}
            # Record tool definitions if present
            tools = invocation_params.get("tools") or []
            if not tools:
                # Attempt to discover tool list on instance (common after bind_tools)
                for k, v in getattr(instance, "__dict__", {}).items():
                    if (
                        isinstance(v, list)
                        and v
                        and all(hasattr(t, "name") for t in v)
                    ):
                        tools = v
                        break
            for idx, tool in enumerate(tools):
                try:
                    if isinstance(tool, dict):
                        fn = (
                            tool.get("function")
                            if isinstance(tool, dict)
                            else None
                        )
                        if not fn:
                            continue
                        name = fn.get("name")
                        desc = fn.get("description")
                        params = fn.get("parameters")
                    else:
                        name = getattr(tool, "name", None)
                        desc = getattr(tool, "description", None) or (
                            tool.__doc__.strip()
                            if getattr(tool, "__doc__", None)
                            else None
                        )
                        params = None
                        args_schema = getattr(tool, "args_schema", None)
                        if args_schema is not None:
                            try:
                                # pydantic v1/v2 compatibility
                                if hasattr(args_schema, "model_json_schema"):
                                    params = args_schema.model_json_schema()
                                elif hasattr(args_schema, "schema"):  # legacy
                                    params = args_schema.schema()
                            except Exception:
                                pass
                    if name:
                        attrs[f"gen_ai.request.function.{idx}.name"] = name
                    if desc:
                        attrs[f"gen_ai.request.function.{idx}.description"] = (
                            desc
                        )
                    if params is not None:
                        try:
                            attrs[
                                f"gen_ai.request.function.{idx}.parameters"
                            ] = json.dumps(params)
                        except Exception:
                            attrs[
                                f"gen_ai.request.function.{idx}.parameters"
                            ] = str(params)
                except Exception:
                    continue
            inv = UtilLLMInvocation(
                request_model=request_model,
                provider=None,
                input_messages=_build_input_messages(messages),
                attributes=attrs,
            )
            self._telemetry_handler.start_llm(inv)
            # Emit log events for input messages (system/human)
            try:
                event_logger = self._telemetry_handler._event_logger  # noqa: SLF001
                for m in inv.input_messages:
                    role = m.role
                    if role in ("system", "human", "user"):
                        event_name = f"gen_ai.{ 'human' if role in ('human','user') else 'system' }.message"
                        body = {
                            "content": m.parts[0].content if m.parts else None
                        }
                        event_logger.emit(event_name, body=body)
            except Exception:  # pragma: no cover
                pass
            return inv

        def _finish_invocation(inv, response):
            content_text, finish_reason, usage = _extract_generation_data(
                response
            )
            if content_text is not None:
                inv.output_messages = [
                    UtilOutputMessage(
                        role="assistant",
                        parts=[UtilText(content=str(content_text))],
                        finish_reason=finish_reason,
                    )
                ]
            # Response metadata mapping
            try:
                llm_output = getattr(response, "llm_output", None) or {}
                inv.response_model_name = llm_output.get(
                    "model"
                ) or llm_output.get("model_name")
                inv.response_id = llm_output.get("id")
                if inv.response_model_name:
                    inv.attributes[GenAIAttr.GEN_AI_RESPONSE_MODEL] = (
                        inv.response_model_name
                    )
                if inv.response_id:
                    inv.attributes[GenAIAttr.GEN_AI_RESPONSE_ID] = (
                        inv.response_id
                    )
            except Exception:
                pass
            _apply_usage(inv, usage)
            if inv.input_tokens is not None:
                inv.attributes[GenAIAttr.GEN_AI_USAGE_INPUT_TOKENS] = (
                    inv.input_tokens
                )
            if inv.output_tokens is not None:
                inv.attributes[GenAIAttr.GEN_AI_USAGE_OUTPUT_TOKENS] = (
                    inv.output_tokens
                )
            if inv.input_tokens is None:
                inv.input_tokens = 1
            if inv.output_tokens is None:
                inv.output_tokens = 1
            self._telemetry_handler.stop_llm(inv)
            # Emit choice log event
            try:
                event_logger = self._telemetry_handler._event_logger  # noqa: SLF001
                if inv.output_messages:
                    event_logger.emit(
                        "gen_ai.choice",
                        body={
                            "index": 0,
                            "finish_reason": finish_reason,
                            "message": {
                                "content": inv.output_messages[0]
                                .parts[0]
                                .content
                                if inv.output_messages[0].parts
                                else None,
                                "type": "ChatGeneration",
                            },
                        },
                    )
            except Exception:  # pragma: no cover
                pass
            try:
                self._telemetry_handler.evaluate_llm(inv)
            except Exception:  # pragma: no cover
                pass

        def _generate_wrapper(wrapped, instance, args, kwargs):
            messages = args[0] if args else kwargs.get("messages")
            invocation_params = kwargs.get("invocation_params") or {}
            inv = _start_invocation(instance, messages, invocation_params)
            try:
                response = wrapped(*args, **kwargs)
                _finish_invocation(inv, response)
                return response
            except Exception as e:  # noqa: BLE001
                self._telemetry_handler.fail_llm(
                    inv, UtilError(message=str(e), type=type(e))
                )
                raise

        async def _agenerate_wrapper(wrapped, instance, args, kwargs):
            messages = args[0] if args else kwargs.get("messages")
            invocation_params = kwargs.get("invocation_params") or {}
            inv = _start_invocation(instance, messages, invocation_params)
            try:
                response = await wrapped(*args, **kwargs)
                _finish_invocation(inv, response)
                return response
            except Exception as e:  # noqa: BLE001
                self._telemetry_handler.fail_llm(
                    inv, UtilError(message=str(e), type=type(e))
                )
                raise

        # Wrap generation methods
        try:
            wrap_function_wrapper(
                module="langchain_openai.chat_models.base",
                name="BaseChatOpenAI._generate",
                wrapper=_generate_wrapper,
            )
        except Exception:  # pragma: no cover
            pass
        try:
            wrap_function_wrapper(
                module="langchain_openai.chat_models.base",
                name="BaseChatOpenAI._agenerate",
                wrapper=_agenerate_wrapper,
            )
        except Exception:  # pragma: no cover
            pass

    def _uninstrument(self, **kwargs):
        # Unwrap generation methods
        unwrap("langchain_openai.chat_models.base", "BaseChatOpenAI._generate")
        unwrap(
            "langchain_openai.chat_models.base", "BaseChatOpenAI._agenerate"
        )

class _BaseCallbackManagerInitWrapper:
    """
    Wrap the BaseCallbackManager __init__ to insert
    custom callback handler in the manager's handlers list.
    """

    def __init__(self, callback_handler):
        self._otel_handler = callback_handler

    def __call__(self, wrapped, instance, args, kwargs):
        wrapped(*args, **kwargs)
        # Ensure our OTel callback is present if not already.
        for handler in instance.inheritable_handlers:
            if isinstance(handler, type(self._otel_handler)):
                break
        else:
            instance.add_handler(self._otel_handler, inherit=True)
