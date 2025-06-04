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

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.instrumentation.langchain.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.trace import get_tracer
from opentelemetry._events import get_event_logger

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
        )

        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
        )

        event_logger_provider = kwargs.get("event_logger_provider")
        event_logger = get_event_logger(
            __name__,
            __version__,
            event_logger_provider=event_logger_provider,
        )

    def _uninstrument(self, **kwargs):
        """
        Cleanup instrumentation (unwrap).
        """
        unwrap("langchain_core.callbacks.base", "BaseCallbackManager.__init__")
        if not self._disable_trace_injection:
            unwrap("langchain_openai.chat_models.base", "BaseChatOpenAI._generate")
            unwrap("langchain_openai.chat_models.base", "BaseChatOpenAI._agenerate")