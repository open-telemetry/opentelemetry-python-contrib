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
OpenTelemetry Anthropic Instrumentation
========================================

Instrumentation for the Anthropic Python SDK.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
    import anthropic

    # Enable instrumentation
    AnthropicInstrumentor().instrument()

    # Use Anthropic client normally
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello!"}]
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.anthropic.package import _instruments
from opentelemetry.instrumentation.anthropic.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

# Methods to wrap - sync
WRAPPED_METHODS = [
    {
        "package": "anthropic.resources.messages",
        "object": "Messages",
        "method": "create",
        "wrapper": "messages_create",
    },
    {
        "package": "anthropic.resources.messages",
        "object": "Messages",
        "method": "stream",
        "wrapper": "messages_stream",
    },
    # AsyncMessages.stream is a sync method returning async context manager
    {
        "package": "anthropic.resources.messages",
        "object": "AsyncMessages",
        "method": "stream",
        "wrapper": "async_messages_stream",
    },
    # Beta API methods
    {
        "package": "anthropic.resources.beta.messages.messages",
        "object": "Messages",
        "method": "create",
        "wrapper": "messages_create",
    },
    {
        "package": "anthropic.resources.beta.messages.messages",
        "object": "Messages",
        "method": "stream",
        "wrapper": "messages_stream",
    },
    # Bedrock SDK Beta methods
    {
        "package": "anthropic.lib.bedrock._beta_messages",
        "object": "Messages",
        "method": "create",
        "wrapper": "messages_create",
    },
    {
        "package": "anthropic.lib.bedrock._beta_messages",
        "object": "Messages",
        "method": "stream",
        "wrapper": "messages_stream",
    },
]

# Methods to wrap - async
WRAPPED_AMETHODS = [
    {
        "package": "anthropic.resources.messages",
        "object": "AsyncMessages",
        "method": "create",
        "wrapper": "async_messages_create",
    },
    # Beta API async methods
    {
        "package": "anthropic.resources.beta.messages.messages",
        "object": "AsyncMessages",
        "method": "create",
        "wrapper": "async_messages_create",
    },
    {
        "package": "anthropic.resources.beta.messages.messages",
        "object": "AsyncMessages",
        "method": "stream",
        "wrapper": "async_messages_stream",
    },
    # Bedrock SDK Beta async methods
    {
        "package": "anthropic.lib.bedrock._beta_messages",
        "object": "AsyncMessages",
        "method": "create",
        "wrapper": "async_messages_create",
    },
    {
        "package": "anthropic.lib.bedrock._beta_messages",
        "object": "AsyncMessages",
        "method": "stream",
        "wrapper": "async_messages_stream",
    },
]


class AnthropicInstrumentor(BaseInstrumentor):
    """An instrumentor for the Anthropic Python SDK.

    This instrumentor will automatically trace Anthropic API calls and
    optionally capture message content as events.
    """

    def __init__(
        self,
        exception_logger: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__()
        self._tracer = None
        self._event_logger = None
        self._meter = None
        self._instruments = None
        self._exception_logger = exception_logger

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Anthropic instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
                - meter_provider: MeterProvider instance
                - logger_provider: LoggerProvider instance
        """
        from opentelemetry._logs import get_logger
        from opentelemetry.metrics import get_meter
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.anthropic.instruments import (
            Instruments,
        )
        from opentelemetry.instrumentation.anthropic.patch import (
            async_messages_create_wrapper,
            async_messages_stream_wrapper,
            messages_create_wrapper,
            messages_stream_wrapper,
        )
        from opentelemetry.instrumentation.anthropic.utils import Config

        # Set exception logger
        if self._exception_logger:
            Config.exception_logger = self._exception_logger

        # Get providers from kwargs
        tracer_provider = kwargs.get("tracer_provider")
        logger_provider = kwargs.get("logger_provider")
        meter_provider = kwargs.get("meter_provider")

        # Initialize tracer
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Initialize logger for events
        event_logger = get_logger(
            __name__,
            __version__,
            schema_url=Schemas.V1_28_0.value,
            logger_provider=logger_provider,
        )

        # Initialize meter for metrics
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Create instruments
        instruments = Instruments(meter)

        # Store for later use
        self._tracer = tracer
        self._event_logger = event_logger
        self._meter = meter
        self._instruments = instruments

        # Map wrapper names to functions
        wrapper_map = {
            "messages_create": messages_create_wrapper(
                tracer, instruments, event_logger
            ),
            "messages_stream": messages_stream_wrapper(
                tracer, instruments, event_logger
            ),
            "async_messages_create": async_messages_create_wrapper(
                tracer, instruments, event_logger
            ),
            "async_messages_stream": async_messages_stream_wrapper(
                tracer, instruments, event_logger
            ),
        }

        # Wrap sync methods
        for method_info in WRAPPED_METHODS:
            wrap_package = method_info["package"]
            wrap_object = method_info["object"]
            wrap_method = method_info["method"]
            wrapper_name = method_info["wrapper"]

            try:
                wrap_function_wrapper(
                    wrap_package,
                    f"{wrap_object}.{wrap_method}",
                    wrapper_map[wrapper_name],
                )
                logger.debug(
                    "Successfully wrapped %s.%s.%s",
                    wrap_package,
                    wrap_object,
                    wrap_method,
                )
            except Exception as e:
                logger.debug(
                    "Failed to wrap %s.%s.%s: %s",
                    wrap_package,
                    wrap_object,
                    wrap_method,
                    e,
                )

        # Wrap async methods
        for method_info in WRAPPED_AMETHODS:
            wrap_package = method_info["package"]
            wrap_object = method_info["object"]
            wrap_method = method_info["method"]
            wrapper_name = method_info["wrapper"]

            try:
                wrap_function_wrapper(
                    wrap_package,
                    f"{wrap_object}.{wrap_method}",
                    wrapper_map[wrapper_name],
                )
                logger.debug(
                    "Successfully wrapped %s.%s.%s",
                    wrap_package,
                    wrap_object,
                    wrap_method,
                )
            except Exception as e:
                logger.debug(
                    "Failed to wrap %s.%s.%s: %s",
                    wrap_package,
                    wrap_object,
                    wrap_method,
                    e,
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Anthropic instrumentation.

        This removes all patches applied during instrumentation.
        """
        for method_info in WRAPPED_METHODS:
            wrap_package = method_info["package"]
            wrap_object = method_info["object"]
            wrap_method = method_info["method"]
            try:
                unwrap(f"{wrap_package}.{wrap_object}", wrap_method)
            except Exception:
                pass

        for method_info in WRAPPED_AMETHODS:
            wrap_package = method_info["package"]
            wrap_object = method_info["object"]
            wrap_method = method_info["method"]
            try:
                unwrap(f"{wrap_package}.{wrap_object}", wrap_method)
            except Exception:
                pass
