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
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap


from opentelemetry.genai.sdk.api import get_telemetry_client
from opentelemetry.genai.sdk.api import TelemetryClient
from .utils import (
    should_emit_events,
    get_evaluation_framework_name,
)
from opentelemetry.genai.sdk.evals import (
    get_evaluator,
)

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

        self._telemetry: TelemetryClient | None = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        exporter_type_full = should_emit_events()

        # Instantiate a singleton TelemetryClient bound to our tracer & meter
        self._telemetry = get_telemetry_client(exporter_type_full, **kwargs)

        # initialize evaluation framework if needed
        evaluation_framework_name = get_evaluation_framework_name()
        # TODO: add check for OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE
        self._evaluation = get_evaluator(evaluation_framework_name)

        otel_callback_handler = OpenTelemetryLangChainCallbackHandler(
            telemetry_client=self._telemetry,
            evaluation_client=self._evaluation,
        )

        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(otel_callback_handler),
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