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
Cohere client instrumentation supporting `cohere`, it can be enabled by
using ``CohereInstrumentor``.

.. _openai: https://pypi.org/project/cohere/

Usage
-----

.. code:: python

    import cohere
    from opentelemetry.instrumentation.cohere_v2 import CohereInstrumentor

    CohereInstrumentor().instrument()

    co = cohere.ClientV2('<your-api-key>')

    response = co.chat(
        model="command-r-plus", 
        messages=[{"role": "user", "content": "Write a short poem on OpenTelemetry."}]
    )

API
---
"""

from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry._events import get_event_logger
from opentelemetry.instrumentation.genai_utils import is_content_enabled
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.cohere_v2.package import _instruments
from opentelemetry.instrumentation.cohere_v2.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .patch import client_chat


class CohereInstrumentor(BaseInstrumentor):
    """An instrumentor for Cohere's client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable Cohere instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )
        event_logger_provider = kwargs.get("event_logger_provider")
        event_logger = get_event_logger(
            __name__,
            __version__,
            schema_url=Schemas.V1_28_0.value,
            event_logger_provider=event_logger_provider,
        )

        wrap_function_wrapper(
            module="cohere.client_v2",
            name="ClientV2.chat",
            wrapper=client_chat(
                tracer, event_logger, is_content_enabled()
            ),
        )


    def _uninstrument(self, **kwargs):
        import cohere  # pylint: disable=import-outside-toplevel

        unwrap("cohere.client_v2.ClientV2", "chat")
