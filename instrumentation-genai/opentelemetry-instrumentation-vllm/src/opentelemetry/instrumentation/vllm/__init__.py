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
vLLM server-side instrumentation supporting `vllm`, it can be enabled by
using ``VLLMInstrumentor``.

.. _vllm: https://pypi.org/project/vllm/

Unlike other GenAI instrumentations in this repository which are client-side,
this is a **server-side** instrumentation for the vLLM inference engine.
It records server-side metrics including time-to-first-token (TTFT) and
time-per-output-token (TPOT).

Metrics and span attributes follow the OpenTelemetry GenAI semantic conventions:
https://opentelemetry.io/docs/specs/semconv/gen-ai/

Usage
-----

.. code:: python

    from vllm import LLM
    from opentelemetry.instrumentation.vllm import VLLMInstrumentor

    VLLMInstrumentor().instrument()

    llm = LLM(model="meta-llama/Llama-2-7b-hf")
    outputs = llm.generate(["Hello, world!"])

API
---
"""

import logging
from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.vllm.package import _instruments
from opentelemetry.metrics import get_meter
from opentelemetry.trace import get_tracer

from .instruments import Instruments
from .patch import chat_wrapper, generate_wrapper

logger = logging.getLogger(__name__)


class VLLMInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for vLLM inference engine.

    Wraps ``vllm.LLM.generate()`` and ``vllm.LLM.chat()`` to emit
    OpenTelemetry spans and metrics following GenAI semantic conventions.

    Key server-side metrics:
      - ``gen_ai.server.time_to_first_token`` — TTFT histogram
      - ``gen_ai.server.time_per_output_token`` — TPOT histogram
      - ``gen_ai.client.operation.duration`` — operation duration
      - ``gen_ai.client.token.usage`` — token usage histogram
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable vLLM instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, "", tracer_provider)

        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(__name__, "", meter_provider)
        instruments = Instruments(meter)

        wrap_function_wrapper(
            module="vllm",
            name="LLM.generate",
            wrapper=generate_wrapper(tracer, instruments),
        )

        wrap_function_wrapper(
            module="vllm",
            name="LLM.chat",
            wrapper=chat_wrapper(tracer, instruments),
        )

    def _uninstrument(self, **kwargs):
        import vllm  # pylint: disable=import-outside-toplevel

        from opentelemetry.instrumentation.utils import unwrap

        unwrap(vllm.LLM, "generate")
        unwrap(vllm.LLM, "chat")
