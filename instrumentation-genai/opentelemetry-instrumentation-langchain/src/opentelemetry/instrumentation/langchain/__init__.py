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

from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.instrumentation.langchain.package import _instruments
from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from opentelemetry.trace import set_span_in_context
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.trace import get_tracer
from opentelemetry._events import get_event_logger
from opentelemetry.semconv.schemas import Schemas

from .instruments import Instruments


class LangChainInstrumentor(BaseInstrumentor):
    """
    OpenTelemetry instrumentor for LangChain.

    This adds a custom callback handler to the LangChain callback manager
    to capture chain, LLM, and tool events. It also wraps the internal
    OpenAI invocation points (BaseChatOpenAI) to inject W3C trace headers
    for downstream calls to OpenAI (or other providers).
    """

    def __init__(self, exception_logger=None, disable_trace_injection: bool = False):
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
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        event_logger_provider = kwargs.get("event_logger_provider")
        event_logger = get_event_logger(
            __name__,
            __version__,
            event_logger_provider=event_logger_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        instruments = Instruments(meter)

        otel_callback_handler = OpenTelemetryLangChainCallbackHandler(
            tracer=tracer,
            instruments=instruments,
            event_logger = event_logger,
        )

        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(otel_callback_handler),
        )

        # Optionally wrap LangChain's "BaseChatOpenAI" methods to inject trace context
        if not self._disable_trace_injection:
            wrap_function_wrapper(
                module="langchain_openai.chat_models.base",
                name="BaseChatOpenAI._generate",
                wrapper=_OpenAITraceInjectionWrapper(otel_callback_handler),
            )
            wrap_function_wrapper(
                module="langchain_openai.chat_models.base",
                name="BaseChatOpenAI._agenerate",
                wrapper=_OpenAITraceInjectionWrapper(otel_callback_handler),
            )

    def _uninstrument(self, **kwargs):
        """
        Cleanup instrumentation (unwrap).
        """
        unwrap("langchain_core.callbacks.base", "BaseCallbackManager.__init__")
        if not self._disable_trace_injection:
            unwrap("langchain_openai.chat_models.base", "BaseChatOpenAI._generate")
            unwrap("langchain_openai.chat_models.base", "BaseChatOpenAI._agenerate")


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


class _OpenAITraceInjectionWrapper:
    """
    A wrapper that intercepts calls to the underlying LLM code in LangChain
    to inject W3C trace headers into upstream requests (if possible).
    """

    def __init__(self, callback_manager):
        self._otel_handler = callback_manager

    def __call__(self, wrapped, instance, args, kwargs):
        """
        Look up the run_id in the `kwargs["run_manager"]` to find
        the active span from the callback handler. Then inject
        that span context into the 'extra_headers' for the openai call.
        """
        run_manager = kwargs.get("run_manager")
        if run_manager is not None:
            run_id = run_manager.run_id
            span_holder = self._otel_handler.spans.get(run_id)
            if span_holder and span_holder.span.is_recording():
                extra_headers = kwargs.get("extra_headers", {})
                ctx = set_span_in_context(span_holder.span)
                TraceContextTextMapPropagator().inject(extra_headers, context=ctx)
                kwargs["extra_headers"] = extra_headers

        return wrapped(*args, **kwargs)