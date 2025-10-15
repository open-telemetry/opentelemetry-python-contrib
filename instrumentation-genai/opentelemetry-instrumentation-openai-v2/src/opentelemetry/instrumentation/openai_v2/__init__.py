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
    
    # Chat completions API
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )
    
    # Responses API
    response = client.responses.create(
        model="gpt-4o-mini",
        input="Write a short poem on open telemetry.",
    )

API
---
"""

from typing import Collection

from packaging import version as package_version
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
    async_responses_create,
    chat_completions_create,
    responses_create,
)


def _is_responses_api_supported():
    """Check if the installed OpenAI version supports the responses API."""
    try:
        import openai  # pylint: disable=import-outside-toplevel

        return package_version.parse(openai.__version__) >= package_version.parse(
            "1.66.0"
        )
    except Exception:  # pylint: disable=broad-except
        return False


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

        # Only instrument responses API if supported (OpenAI >= 1.66.0)
        if _is_responses_api_supported():
            wrap_function_wrapper(
                module="openai.resources.responses.responses",
                name="Responses.create",
                wrapper=responses_create(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )

            wrap_function_wrapper(
                module="openai.resources.responses.responses",
                name="AsyncResponses.create",
                wrapper=async_responses_create(
                    tracer, logger, instruments, is_content_enabled()
                ),
            )

    def _uninstrument(self, **kwargs):
        import openai  # pylint: disable=import-outside-toplevel

        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")
        
        # Only uninstrument responses API if supported (OpenAI >= 1.66.0)
        if _is_responses_api_supported():
            unwrap(openai.resources.responses.responses.Responses, "create")
            unwrap(openai.resources.responses.responses.AsyncResponses, "create")
