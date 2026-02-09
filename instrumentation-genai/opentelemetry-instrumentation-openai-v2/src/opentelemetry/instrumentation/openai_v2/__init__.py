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

from .instruments import Instruments
from .patch import (
    async_chat_completions_create,
    async_embeddings_create,
    chat_completions_create,
    embeddings_create,
    responses_create,
    responses_retrieve,
    responses_stream,
)


class OpenAIInstrumentor(BaseInstrumentor):
    def __init__(self):
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable OpenAI instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_30_0.value,
        )
        logger_provider = kwargs.get("logger_provider")
        logger = get_logger(
            __name__,
            "",
            schema_url=Schemas.V1_30_0.value,
            logger_provider=logger_provider,
        )
        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            "",
            meter_provider,
            schema_url=Schemas.V1_30_0.value,
        )

        instruments = Instruments(self._meter)

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="Completions.create",
            wrapper=chat_completions_create(
                tracer, logger, instruments, is_content_enabled()
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="AsyncCompletions.create",
            wrapper=async_chat_completions_create(
                tracer, logger, instruments, is_content_enabled()
            ),
        )

        # Add instrumentation for the embeddings API
        wrap_function_wrapper(
            module="openai.resources.embeddings",
            name="Embeddings.create",
            wrapper=embeddings_create(
                tracer, instruments, is_content_enabled()
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.embeddings",
            name="AsyncEmbeddings.create",
            wrapper=async_embeddings_create(
                tracer, instruments, is_content_enabled()
            ),
        )

        # Responses API is only available in openai>=1.66.0
        # https://github.com/openai/openai-python/blob/main/CHANGELOG.md#1660-2025-03-11
        try:
            wrap_function_wrapper(
                module="openai.resources.responses.responses",
                name="Responses.create",
                wrapper=responses_create(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )

            wrap_function_wrapper(
                module="openai.resources.responses.responses",
                name="Responses.stream",
                wrapper=responses_stream(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )

            wrap_function_wrapper(
                module="openai.resources.responses.responses",
                name="Responses.retrieve",
                wrapper=responses_retrieve(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )
        except (AttributeError, ModuleNotFoundError):
            # Responses API not available in this version of openai
            pass

    def _uninstrument(self, **kwargs):
        import openai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")
        unwrap(openai.resources.embeddings.Embeddings, "create")
        unwrap(openai.resources.embeddings.AsyncEmbeddings, "create")

        # Responses API is only available in openai>=1.66.0
        # https://github.com/openai/openai-python/blob/main/CHANGELOG.md#1660-2025-03-11
        try:
            unwrap(openai.resources.responses.responses.Responses, "create")
            unwrap(openai.resources.responses.responses.Responses, "stream")
            unwrap(openai.resources.responses.responses.Responses, "retrieve")
        except (AttributeError, ModuleNotFoundError):
            # Responses API not available in this version of openai
            pass
