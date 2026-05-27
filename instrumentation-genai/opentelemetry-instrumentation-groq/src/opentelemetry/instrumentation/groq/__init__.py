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
OpenTelemetry Groq Instrumentation
====================================

Instrumentation for the Groq Python SDK.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.groq import GroqInstrumentor
    import groq

    # Enable instrumentation
    GroqInstrumentor().instrument()

    # Use Groq client normally
    client = groq.Groq()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Hello!"}],
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

from opentelemetry.instrumentation.groq.package import _instruments
from opentelemetry.instrumentation.groq.patch import (
    async_chat_completions_create,
    chat_completions_create,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.handler import TelemetryHandler


class GroqInstrumentor(BaseInstrumentor):
    """An instrumentor for the Groq Python SDK.

    Automatically traces Groq API calls and records operation duration and
    token usage metrics. Optionally captures message content as span attributes.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Groq instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
                - meter_provider: MeterProvider instance
                - logger_provider: LoggerProvider instance
        """
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
        )

        wrap_function_wrapper(
            module="groq.resources.chat.completions",
            name="Completions.create",
            wrapper=chat_completions_create(handler),
        )
        wrap_function_wrapper(
            module="groq.resources.chat.completions",
            name="AsyncCompletions.create",
            wrapper=async_chat_completions_create(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Groq instrumentation."""
        import groq  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(
            groq.resources.chat.completions.Completions,  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownArgumentType]
            "create",
        )
        unwrap(
            groq.resources.chat.completions.AsyncCompletions,  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownArgumentType]
            "create",
        )
