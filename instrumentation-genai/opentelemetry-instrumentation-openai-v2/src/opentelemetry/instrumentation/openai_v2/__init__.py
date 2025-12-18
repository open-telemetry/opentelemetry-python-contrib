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

import importlib
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
    async_responses_compact,
    async_responses_create,
    responses_compact,
    responses_create,
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
            schema_url=Schemas.V1_28_0.value,
        )
        logger_provider = kwargs.get("logger_provider")
        logger = get_logger(
            __name__,
            "",
            schema_url=Schemas.V1_28_0.value,
            logger_provider=logger_provider,
        )
        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            "",
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
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

        # Add instrumentation for the Responses API
        wrap_function_wrapper(
            module="openai.resources.responses",
            name="Responses.create",
            wrapper=responses_create(
                tracer, logger, instruments, is_content_enabled()
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.responses",
            name="AsyncResponses.create",
            wrapper=async_responses_create(
                tracer, logger, instruments, is_content_enabled()
            ),
        )

        # `Responses.compact` was added later in openai-python; guard so older
        # supported versions don't fail instrumentation.
        try:
            wrap_function_wrapper(
                module="openai.resources.responses",
                name="Responses.compact",
                wrapper=responses_compact(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )
            wrap_function_wrapper(
                module="openai.resources.responses",
                name="AsyncResponses.compact",
                wrapper=async_responses_compact(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )
        except AttributeError:
            pass

    def _uninstrument(self, **kwargs):
        chat_mod = importlib.import_module("openai.resources.chat.completions")
        unwrap(chat_mod.Completions, "create")
        unwrap(chat_mod.AsyncCompletions, "create")

        embeddings_mod = importlib.import_module("openai.resources.embeddings")
        unwrap(embeddings_mod.Embeddings, "create")
        unwrap(embeddings_mod.AsyncEmbeddings, "create")

        responses_mod = importlib.import_module("openai.resources.responses")
        unwrap(responses_mod.Responses, "create")
        unwrap(responses_mod.AsyncResponses, "create")
        if hasattr(responses_mod.Responses, "compact"):
            unwrap(responses_mod.Responses, "compact")
        if hasattr(responses_mod.AsyncResponses, "compact"):
            unwrap(responses_mod.AsyncResponses, "compact")
