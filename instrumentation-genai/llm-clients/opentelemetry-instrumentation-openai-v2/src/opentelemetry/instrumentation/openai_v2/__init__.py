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

Configuration
-------------

The following configuration options are available:

- ``enable_trace_context_propagation``: If True, inject W3C trace context
  into OpenAI request headers. Default: False.

API
---
"""

import logging
from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.openai_v2.package import _instruments
from opentelemetry.instrumentation.openai_v2.utils import (
    CaptureMode,
    get_capture_mode,
)
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
)

logger = logging.getLogger(__name__)


class OpenAIInstrumentor(BaseInstrumentor):
    """An instrumentor for OpenAI's client library.

    Args:
        enable_trace_context_propagation: If True, inject W3C trace context
            into OpenAI request headers for end-to-end tracing.
            Default: False.
    """

    def __init__(self, enable_trace_context_propagation: bool = False):
        super().__init__()
        self._meter = None
        self._enable_trace_context_propagation = enable_trace_context_propagation

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
        event_logger = get_logger(
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
        capture_mode = get_capture_mode("openai")

        # Chat Completions API
        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="Completions.create",
            wrapper=chat_completions_create(
                tracer,
                event_logger,
                instruments,
                capture_mode,
                self._enable_trace_context_propagation,
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="AsyncCompletions.create",
            wrapper=async_chat_completions_create(
                tracer,
                event_logger,
                instruments,
                capture_mode,
                self._enable_trace_context_propagation,
            ),
        )

        # Embeddings API
        wrap_function_wrapper(
            module="openai.resources.embeddings",
            name="Embeddings.create",
            wrapper=embeddings_create(tracer, instruments, capture_mode),
        )

        wrap_function_wrapper(
            module="openai.resources.embeddings",
            name="AsyncEmbeddings.create",
            wrapper=async_embeddings_create(
                tracer, instruments, capture_mode
            ),
        )

        # Completions API (Legacy text completions)
        self._wrap_completions_api(tracer, event_logger, instruments, capture_mode)

        # Images API
        self._wrap_images_api(tracer, instruments, capture_mode)

        # Responses API
        self._wrap_responses_api(tracer, event_logger, instruments, capture_mode)

    def _wrap_completions_api(self, tracer, event_logger, instruments, capture_mode):
        """Wrap the legacy Completions API."""
        try:
            from .completions_patch import (
                async_completions_create,
                completions_create,
            )

            wrap_function_wrapper(
                module="openai.resources.completions",
                name="Completions.create",
                wrapper=completions_create(
                    tracer, event_logger, instruments, capture_mode
                ),
            )

            wrap_function_wrapper(
                module="openai.resources.completions",
                name="AsyncCompletions.create",
                wrapper=async_completions_create(
                    tracer, event_logger, instruments, capture_mode
                ),
            )
        except (ImportError, AttributeError) as e:
            logger.debug("Could not wrap Completions API: %s", e)

    def _wrap_images_api(self, tracer, instruments, capture_mode):
        """Wrap the Images API."""
        try:
            from .images_patch import async_images_generate, images_generate

            wrap_function_wrapper(
                module="openai.resources.images",
                name="Images.generate",
                wrapper=images_generate(tracer, instruments, capture_mode),
            )

            wrap_function_wrapper(
                module="openai.resources.images",
                name="AsyncImages.generate",
                wrapper=async_images_generate(
                    tracer, instruments, capture_mode
                ),
            )
        except (ImportError, AttributeError) as e:
            logger.debug("Could not wrap Images API: %s", e)

    def _wrap_responses_api(self, tracer, event_logger, instruments, capture_mode):
        """Wrap the Responses API."""
        try:
            from .responses_patch import (
                async_responses_create,
                responses_create,
            )

            wrap_function_wrapper(
                module="openai.resources.responses",
                name="Responses.create",
                wrapper=responses_create(
                    tracer, event_logger, instruments, capture_mode
                ),
            )

            wrap_function_wrapper(
                module="openai.resources.responses",
                name="AsyncResponses.create",
                wrapper=async_responses_create(
                    tracer, event_logger, instruments, capture_mode
                ),
            )
        except (ImportError, AttributeError) as e:
            logger.debug("Could not wrap Responses API: %s", e)

    def _uninstrument(self, **kwargs):
        import openai  # pylint: disable=import-outside-toplevel

        # Chat Completions
        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")

        # Embeddings
        unwrap(openai.resources.embeddings.Embeddings, "create")
        unwrap(openai.resources.embeddings.AsyncEmbeddings, "create")

        # Completions (Legacy)
        try:
            unwrap(openai.resources.completions.Completions, "create")
            unwrap(openai.resources.completions.AsyncCompletions, "create")
        except (ImportError, AttributeError):
            pass

        # Images
        try:
            unwrap(openai.resources.images.Images, "generate")
            unwrap(openai.resources.images.AsyncImages, "generate")
        except (ImportError, AttributeError):
            pass

        # Responses
        try:
            unwrap(openai.resources.responses.Responses, "create")
            unwrap(openai.resources.responses.AsyncResponses, "create")
        except (ImportError, AttributeError):
            pass
