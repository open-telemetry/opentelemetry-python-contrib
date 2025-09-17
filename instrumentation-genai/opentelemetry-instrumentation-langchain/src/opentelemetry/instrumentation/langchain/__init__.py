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
Langchain instrumentation supporting `ChatOpenAI` and `ChatBedrock`, it can be enabled by
using ``LangChainInstrumentor``. Other providers/LLMs may be supported in the future and telemetry for them is skipped for now.

Usage
-----
.. code:: python
    from opentelemetry.instrumentation.langchain import LangChainInstrumentor
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    LangChainInstrumentor().instrument()
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, max_tokens=1000)
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]
    result = llm.invoke(messages)
    LangChainInstrumentor().uninstrument()

API
---
"""

from typing import Any, Callable, Collection, Optional

from langchain_core.callbacks import BaseCallbackHandler  # type: ignore
from wrapt import wrap_function_wrapper  # type: ignore

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.package import _instruments
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer


class LangChainInstrumentor(BaseInstrumentor):
    """
    OpenTelemetry instrumentor for LangChain.
    This adds a custom callback handler to the LangChain callback manager
    to capture LLM telemetry.
    """

    def __init__(
        self,
    ):
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """
        Enable Langchain instrumentation.
        """
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_30_0.value,
        )

        otel_callback_handler = OpenTelemetryLangChainCallbackHandler(
            tracer=tracer,
        )

        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(otel_callback_handler),
        )

    def _uninstrument(self, **kwargs: Any):
        """
        Cleanup instrumentation (unwrap).
        """
        unwrap("langchain_core.callbacks.base.BaseCallbackManager", "__init__")


class _BaseCallbackManagerInitWrapper:
    """
    Wrap the BaseCallbackManager __init__ to insert custom callback handler in the manager's handlers list.
    """

    def __init__(
        self, callback_handler: OpenTelemetryLangChainCallbackHandler
    ):
        self._otel_handler = callback_handler

    def __call__(
        self,
        wrapped: Callable[..., None],
        instance: BaseCallbackHandler,  # type: ignore
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ):
        wrapped(*args, **kwargs)
        # Ensure our OTel callback is present if not already.
        for handler in instance.inheritable_handlers:  # type: ignore
            if isinstance(handler, type(self._otel_handler)):
                break
        else:
            instance.add_handler(self._otel_handler, inherit=True)  # type: ignore
