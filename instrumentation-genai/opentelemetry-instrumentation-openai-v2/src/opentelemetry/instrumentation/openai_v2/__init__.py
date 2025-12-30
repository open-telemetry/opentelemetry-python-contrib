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
OpenAI client instrumentation supporting `openai`, it can be enabled by
using ``OpenAIInstrumentor``.

.. _openai: https://pypi.org/project/openai/

Usage
-----

.. code:: python

    from openai import OpenAI
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

API
---
"""

from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.openai_v2.package import _instruments
from opentelemetry.instrumentation.openai_v2.utils import is_content_enabled
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer
from opentelemetry.util.genai.handler import (
    TelemetryHandler,
    get_telemetry_handler,
)
from opentelemetry.util.genai.types import ContentCapturingMode
from opentelemetry.util.genai.utils import (
    get_content_capturing_mode,
    is_experimental_mode,
)

from .instruments import Instruments
from .patch import (
    async_chat_completions_create_v_new,
    async_chat_completions_create_v_old,
    async_embeddings_create,
    chat_completions_create_v_new,
    chat_completions_create_v_old,
    embeddings_create,
)


class OpenAIInstrumentor(BaseInstrumentor):
    def __init__(self):
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable OpenAI instrumentation."""

        latest_experimental_enabled = is_experimental_mode()
        tracer_provider = kwargs.get("tracer_provider")
        schema_url = (
            Schemas.V1_37_0.value
            if latest_experimental_enabled
            else Schemas.V1_30_0.value
        )
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=schema_url,
        )
        logger_provider = kwargs.get("logger_provider")
        logger = get_logger(
            __name__,
            "",
            logger_provider=logger_provider,
            schema_url=schema_url,
        )
        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            "",
            meter_provider,
            schema_url=schema_url,
        )

        instruments = Instruments(self._meter)

        content_mode = (
            get_content_capturing_mode()
            if latest_experimental_enabled
            else ContentCapturingMode.NO_CONTENT
        )
        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="Completions.create",
            wrapper=chat_completions_create_v_new(handler, content_mode)
            if latest_experimental_enabled
            else chat_completions_create_v_old(
                tracer, logger, instruments, is_content_enabled()
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="AsyncCompletions.create",
            wrapper=async_chat_completions_create_v_new(handler, content_mode)
            if latest_experimental_enabled
            else async_chat_completions_create_v_old(
                tracer, logger, instruments, is_content_enabled()
            ),
        )

        # Add instrumentation for the embeddings API
        wrap_function_wrapper(
            module="openai.resources.embeddings",
            name="Embeddings.create",
            wrapper=embeddings_create(
                tracer, instruments, latest_experimental_enabled
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.embeddings",
            name="AsyncEmbeddings.create",
            wrapper=async_embeddings_create(
                tracer, instruments, latest_experimental_enabled
            ),
        )

    def _uninstrument(self, **kwargs):
        import openai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")
        unwrap(openai.resources.embeddings.Embeddings, "create")
        unwrap(openai.resources.embeddings.AsyncEmbeddings, "create")
