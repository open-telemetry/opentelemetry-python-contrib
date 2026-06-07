# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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

from typing import Any, Collection

from wrapt import (
    wrap_function_wrapper,  # pyright: ignore[reportUnknownVariableType]
)

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.handler import TelemetryHandler

from .package import _instruments
from .patch import (
    messages_create,
    messages_stream,
)


class AnthropicInstrumentor(BaseInstrumentor):
    """An instrumentor for the Anthropic Python SDK.

    This instrumentor will automatically trace Anthropic API calls and
    optionally capture message content as events.
    """

    def __init__(self) -> None:
        super().__init__()
        self._tracer = None
        self._logger = None
        self._meter = None

    # pylint: disable=no-self-use
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
        # Get providers from kwargs
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")
        logger_provider = kwargs.get("logger_provider")

        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
        )

        # Patch Messages.create and Messages.stream
        wrap_function_wrapper(
            "anthropic.resources.messages",
            "Messages.create",
            messages_create(handler),
        )
        wrap_function_wrapper(
            "anthropic.resources.messages",
            "Messages.stream",
            messages_stream(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Anthropic instrumentation.

        This removes all patches applied during instrumentation.
        """
        import anthropic  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(
            anthropic.resources.messages.Messages,  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownArgumentType]
            "create",
        )
        unwrap(
            anthropic.resources.messages.Messages,  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownArgumentType]
            "stream",
        )
