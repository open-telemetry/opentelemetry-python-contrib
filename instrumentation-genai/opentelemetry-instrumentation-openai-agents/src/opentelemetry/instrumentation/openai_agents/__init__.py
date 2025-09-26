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
OpenAI Agents instrumentation supporting `openai` in agent frameworks.
Enable with ``OpenAIAgentsInstrumentor``.

.. _openai: https://pypi.org/project/openai/

Usage
-----

.. code:: python

    from openai import OpenAI
    from opentelemetry.instrumentation.openai_agents import (
        OpenAIAgentsInstrumentor,
    )

    OpenAIAgentsInstrumentor().instrument()

    # Your OpenAI agents code here
    client = OpenAI()

API
---

This instrumentation captures spans for OpenAI API calls made within
agent frameworks.
It provides detailed tracing information including:

- Request and response content (if configured)
- Token usage metrics
- Model information
- Error handling

Configuration
-------------

Content, metrics, and events are captured by default with no environment configuration.
This library assumes full capture is desired when installed.
"""

import logging
from typing import Collection

from agents.tracing import add_trace_processor

from opentelemetry._events import get_event_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.openai_agents.constants import (
    GenAIEvaluationAttributes,
    GenAIOperationName,
    GenAIOutputType,
    GenAIProvider,
    GenAIToolType,
)
from opentelemetry.instrumentation.openai_agents.genai_semantic_processor import (
    GenAISemanticProcessor,
)
from opentelemetry.instrumentation.openai_agents.package import _instruments
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

__all__ = [
    "OpenAIAgentsInstrumentor",
    "GenAIProvider",
    "GenAIOperationName",
    "GenAIToolType",
    "GenAIOutputType",
    "GenAIEvaluationAttributes",
]

logger = logging.getLogger(__name__)


class OpenAIAgentsInstrumentor(BaseInstrumentor):
    """An instrumentor for OpenAI Agents frameworks."""

    def _instrument(self, **kwargs):
        """Instruments the OpenAI library for agent frameworks."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )
        event_logger_provider = kwargs.get("event_logger_provider")
        event_logger = get_event_logger(
            __name__,
            "",
            schema_url=Schemas.V1_28_0.value,
            event_logger_provider=event_logger_provider,
        )

        add_trace_processor(
            GenAISemanticProcessor(
                tracer=tracer,
                event_logger=event_logger,
            )
        )

    def _uninstrument(self, **kwargs):
        """Uninstruments the OpenAI library for agent frameworks."""
        # No-op: optional processor registry may not be present.
        return

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return list of python packages with versions instrumented."""
        return _instruments
