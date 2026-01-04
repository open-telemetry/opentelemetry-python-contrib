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
LangChain instrumentation for OpenTelemetry.

This instrumentation supports automatic tracing of LangChain operations including:
- LLM calls (ChatOpenAI, ChatAnthropic, ChatBedrock, and 10+ other providers)
- Chain executions (SequentialChain, LLMChain, etc.)
- Tool/function calls
- Agent executions
- LangGraph workflows

Usage
-----
.. code:: python

    from opentelemetry.instrumentation.langchain import LangChainInstrumentor
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    LangChainInstrumentor().instrument()

    llm = ChatOpenAI(model="gpt-4", temperature=0)
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

from langchain_core.callbacks import BaseCallbackHandler  # type: ignore[import-untyped]
from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.package import _instruments
from opentelemetry.instrumentation.langchain.semconv import MeterNames
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer


class LangChainInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for LangChain.

    This instrumentor adds a custom callback handler to the LangChain callback
    manager to capture telemetry for LLM calls, chains, tools, and agents.

    Features:
        - Automatic span creation for all LangChain operations
        - Token usage tracking and metrics
        - Support for 13+ LLM providers
        - Chain/tool/agent hierarchical tracing
        - LangGraph workflow support
        - Event logging for message content

    Example:
        >>> from opentelemetry.instrumentation.langchain import LangChainInstrumentor
        >>> instrumentor = LangChainInstrumentor()
        >>> instrumentor.instrument()
        >>> # Use LangChain as normal
        >>> instrumentor.uninstrument()
    """

    def __init__(
        self,
        exception_logger: Optional[Callable[[Exception], None]] = None,
        use_legacy_attributes: bool = True,
    ):
        """Initialize the LangChain instrumentor.

        Args:
            exception_logger: Optional callable to log instrumentation exceptions.
            use_legacy_attributes: Whether to use legacy span attributes (default True).
                Set to False to use event-based logging instead.
        """
        super().__init__()
        self._exception_logger = exception_logger
        self._use_legacy_attributes = use_legacy_attributes

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the instrumented package dependencies."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable LangChain instrumentation.

        Args:
            **kwargs: Additional configuration options.
                - tracer_provider: Custom TracerProvider
                - meter_provider: Custom MeterProvider
                - logger_provider: Custom LoggerProvider
        """
        # Set up configuration
        Config.exception_logger = self._exception_logger
        Config.use_legacy_attributes = self._use_legacy_attributes

        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")
        logger_provider = kwargs.get("logger_provider")

        # Create tracer
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Create meter and histograms
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
        )

        duration_histogram = meter.create_histogram(
            name=MeterNames.LLM_OPERATION_DURATION,
            description="Duration of LLM operations",
            unit="s",
        )

        token_histogram = meter.create_histogram(
            name=MeterNames.LLM_TOKEN_USAGE,
            description="Token usage for LLM operations",
            unit="{token}",
        )

        # Create event logger if not using legacy attributes
        if not self._use_legacy_attributes:
            Config.event_logger = get_logger(
                __name__,
                __version__,
                logger_provider=logger_provider,
            )

        # Create callback handler
        otel_callback_handler = OpenTelemetryLangChainCallbackHandler(
            tracer=tracer,
            duration_histogram=duration_histogram,
            token_histogram=token_histogram,
        )

        # Wrap BaseCallbackManager.__init__ to inject our handler
        wrap_function_wrapper(
            module="langchain_core.callbacks",
            name="BaseCallbackManager.__init__",
            wrapper=_BaseCallbackManagerInitWrapper(otel_callback_handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable LangChain instrumentation."""
        unwrap(
            "langchain_core.callbacks.base.BaseCallbackManager", "__init__"
        )
        Config.event_logger = None


class _BaseCallbackManagerInitWrapper:
    """Wrapper for BaseCallbackManager.__init__ to inject OTel callback handler."""

    def __init__(
        self, callback_handler: OpenTelemetryLangChainCallbackHandler
    ) -> None:
        """Initialize the wrapper.

        Args:
            callback_handler: The OpenTelemetry callback handler to inject.
        """
        self._otel_handler = callback_handler

    def __call__(
        self,
        wrapped: Callable[..., None],
        instance: BaseCallbackHandler,  # type: ignore[type-arg]
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """Wrap the __init__ method to inject the callback handler.

        Args:
            wrapped: The original __init__ method.
            instance: The BaseCallbackManager instance.
            args: Positional arguments.
            kwargs: Keyword arguments.
        """
        wrapped(*args, **kwargs)
        # Ensure our OTel callback is present if not already
        for handler in instance.inheritable_handlers:  # type: ignore[attr-defined]
            if isinstance(handler, type(self._otel_handler)):
                break
        else:
            instance.add_handler(self._otel_handler, inherit=True)  # type: ignore[attr-defined]
