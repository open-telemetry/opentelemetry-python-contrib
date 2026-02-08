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
OpenTelemetry Anthropic Agents Instrumentation
===============================================

Instrumentation for the `Claude Agent SDK
<https://github.com/anthropics/claude-agent-sdk-python>`_.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.anthropic_agents import AnthropicAgentsInstrumentor
    from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition, AssistantMessage, TextBlock, query

    # Enable instrumentation
    AnthropicAgentsInstrumentor().instrument()

    # Use Claude Agent SDK normally
    import anyio

    async def main():
        options = ClaudeAgentOptions(
            agents={
                "assistant": AgentDefinition(
                    description="A helpful assistant",
                    prompt="You are a helpful assistant.",
                    tools=["Read"],
                    model="sonnet",
                ),
            },
        )

        async for message in query(prompt="Hello!", options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

    anyio.run(main)

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

from opentelemetry.instrumentation.anthropic_agents.package import _instruments
from opentelemetry.instrumentation.anthropic_agents.patch import messages_create
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.handler import TelemetryHandler


class AnthropicAgentsInstrumentor(BaseInstrumentor):
    """An instrumentor for the Anthropic Python SDK Agents.

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
        """Enable Anthropic Agents instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
                - meter_provider: MeterProvider instance
                - logger_provider: LoggerProvider instance
        """
        # Get providers from kwargs
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")

        # TODO: Add logger_provider to TelemetryHandler to capture content events.
        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )

        # Patch Messages.create
        wrap_function_wrapper(
            module="anthropic.resources.messages",
            name="Messages.create",
            wrapper=messages_create(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Anthropic Agents instrumentation.

        This removes all patches applied during instrumentation.
        """
        import anthropic  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(
            anthropic.resources.messages.Messages,  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownArgumentType]
            "create",
        )
