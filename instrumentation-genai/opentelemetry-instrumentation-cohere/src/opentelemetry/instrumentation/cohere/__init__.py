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

.. _cohere: https://pypi.org/project/cohere/

Usage
-----

.. code:: python

    from cohere import ClientV2
    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()

    client = ClientV2()
    response = client.chat(
        model="command-r-plus",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

API
---
"""

from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.cohere.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import ContentCapturingMode
from opentelemetry.util.genai.utils import (
    get_content_capturing_mode,
    is_experimental_mode,
)

from .patch import (
    async_chat_create,
    chat_create,
)


class CohereInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable Cohere instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")
        logger_provider = kwargs.get("logger_provider")

        latest_experimental_enabled = is_experimental_mode()
        content_mode = (
            get_content_capturing_mode()
            if latest_experimental_enabled
            else ContentCapturingMode.NO_CONTENT
        )

        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
        )

        # Instrument sync V2Client.chat
        wrap_function_wrapper(
            module="cohere.v2.client",
            name="V2Client.chat",
            wrapper=chat_create(handler, content_mode),
        )

        # Instrument async AsyncV2Client.chat
        wrap_function_wrapper(
            module="cohere.v2.client",
            name="AsyncV2Client.chat",
            wrapper=async_chat_create(handler, content_mode),
        )


    def _uninstrument(self, **kwargs):
        import cohere.v2.client  # pylint: disable=import-outside-toplevel

        unwrap(cohere.v2.client.V2Client, "chat")
        unwrap(cohere.v2.client.AsyncV2Client, "chat")
