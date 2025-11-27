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

from typing import Any, Collection

from opentelemetry.instrumentation.anthropic.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.schemas import Schemas


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
        # pylint: disable=import-outside-toplevel
        from opentelemetry._logs import get_logger  # noqa: PLC0415
        from opentelemetry.metrics import get_meter  # noqa: PLC0415
        from opentelemetry.trace import get_tracer  # noqa: PLC0415

        # Get providers from kwargs
        tracer_provider = kwargs.get("tracer_provider")
        logger_provider = kwargs.get("logger_provider")
        meter_provider = kwargs.get("meter_provider")

        # Initialize tracer
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Initialize logger for events
        logger = get_logger(
            __name__,
            "",
            schema_url=Schemas.V1_28_0.value,
            logger_provider=logger_provider,
        )

        # Initialize meter for metrics
        meter = get_meter(
            __name__,
            "",
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Store for later use in _uninstrument
        self._tracer = tracer
        self._logger = logger
        self._meter = meter

        # Patching will be added in Ticket 3

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Anthropic instrumentation.

        This removes all patches applied during instrumentation.
        """
        # Unpatching will be added in Ticket 3
