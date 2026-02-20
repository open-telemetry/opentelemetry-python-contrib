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
OpenTelemetry Claude Agent SDK Instrumentation
==============================================

This package provides automatic instrumentation for the Claude Agent SDK,
capturing telemetry data for agent sessions and tool executions.

Usage
-----

Basic instrumentation::

    from opentelemetry.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor

    # Apply instrumentation
    ClaudeAgentSDKInstrumentor().instrument()

    # Your Claude Agent SDK code works as normal
    from claude_agent_sdk import ClaudeSDKClient

    async with ClaudeSDKClient() as client:
        await client.query(prompt="Hello!")
        async for message in client.receive_response():
            print(message)

The instrumentation automatically captures:

- Agent session spans (invoke_agent)
- Tool execution spans (execute_tool)
- Token usage (input/output tokens)

"""

import logging
from typing import Any, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.claude_agent_sdk.package import _instruments
from opentelemetry.instrumentation.claude_agent_sdk.patch import (
    wrap_claude_client_init,
    wrap_claude_client_query,
    wrap_claude_client_receive_response,
    wrap_query,
)
from opentelemetry.instrumentation.claude_agent_sdk.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.handler import TelemetryHandler
from ._extended_handler import ExtendedTelemetryHandlerForClaude

logger = logging.getLogger(__name__)


class ClaudeAgentSDKInstrumentor(BaseInstrumentor):
    """
    Instrumentor for Claude Agent SDK.
    """

    _handler: Optional[ExtendedTelemetryHandlerForClaude] = None

    def __init__(self):
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the dependencies required for this instrumentation."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """
        Apply instrumentation to Claude Agent SDK.

        Kwargs:
            tracer_provider: Optional TracerProvider to use
            meter_provider: Optional MeterProvider to use
            logger_provider: Optional LoggerProvider to use
        """
        tracer_provider = kwargs.get("tracer_provider")

        base_handler = TelemetryHandler(
            tracer_provider=tracer_provider,
        )
        ClaudeAgentSDKInstrumentor._handler = ExtendedTelemetryHandlerForClaude(base_handler)

        try:
            wrap_function_wrapper(
                module="claude_agent_sdk",
                name="ClaudeSDKClient.__init__",
                wrapper=lambda wrapped,
                instance,
                args,
                kwargs: wrap_claude_client_init(
                    wrapped,
                    instance,
                    args,
                    kwargs,
                    handler=ClaudeAgentSDKInstrumentor._handler,
                ),
            )
        except Exception as e:
            logger.warning(
                f"Failed to instrument ClaudeSDKClient.__init__: {e}"
            )

        try:
            wrap_function_wrapper(
                module="claude_agent_sdk",
                name="ClaudeSDKClient.query",
                wrapper=lambda wrapped,
                instance,
                args,
                kwargs: wrap_claude_client_query(
                    wrapped,
                    instance,
                    args,
                    kwargs,
                    handler=ClaudeAgentSDKInstrumentor._handler,
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to instrument ClaudeSDKClient.query: {e}")

        try:
            wrap_function_wrapper(
                module="claude_agent_sdk",
                name="ClaudeSDKClient.receive_response",
                wrapper=lambda wrapped,
                instance,
                args,
                kwargs: wrap_claude_client_receive_response(
                    wrapped,
                    instance,
                    args,
                    kwargs,
                    handler=ClaudeAgentSDKInstrumentor._handler,
                ),
            )
        except Exception as e:
            logger.warning(
                f"Failed to instrument ClaudeSDKClient.receive_response: {e}"
            )

        try:
            wrap_function_wrapper(
                module="claude_agent_sdk",
                name="query",
                wrapper=lambda wrapped, instance, args, kwargs: wrap_query(
                    wrapped,
                    instance,
                    args,
                    kwargs,
                    handler=ClaudeAgentSDKInstrumentor._handler,
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to instrument claude_agent_sdk.query: {e}")

    def _uninstrument(self, **kwargs: Any) -> None:
        """Remove instrumentation from Claude Agent SDK."""
        try:
            import claude_agent_sdk  # noqa: PLC0415

            # Unwrap all instrumented methods
            unwrap(claude_agent_sdk.ClaudeSDKClient, "__init__")
            unwrap(claude_agent_sdk.ClaudeSDKClient, "query")
            unwrap(claude_agent_sdk.ClaudeSDKClient, "receive_response")
            unwrap(claude_agent_sdk, "query")

        except Exception as e:
            logger.warning(f"Failed to uninstrument Claude Agent SDK: {e}")

        ClaudeAgentSDKInstrumentor._handler = None


__all__ = [
    "__version__",
    "ClaudeAgentSDKInstrumentor",
]
