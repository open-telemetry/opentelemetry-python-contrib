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
Span generation utilities for GenAI telemetry.

This module maps GenAI (Generative AI) invocations to OpenTelemetry spans and
applies GenAI semantic convention attributes.

Classes:
    - BaseTelemetryGenerator: Abstract base for GenAI telemetry emitters.
    - SpanGenerator: Concrete implementation that creates and finalizes spans
      for LLM operations (e.g., chat) and records input/output messages when
      experimental mode and content capture settings allow.

Usage:
    See `opentelemetry/util/genai/handler.py` for `TelemetryHandler`, which
    constructs `LLMInvocation` objects and delegates to `SpanGenerator.start`,
    `SpanGenerator.finish`, and `SpanGenerator.error` to produce spans that
    follow the GenAI semantic conventions.
"""

from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import (
    SpanKind,
    Tracer,
    get_tracer,
    set_span_in_context,
)
from opentelemetry.util.genai.span_utils import (
    _apply_error_attributes,
    _apply_finish_attributes,
)
from opentelemetry.util.genai.types import Error, LLMInvocation
from opentelemetry.util.genai.version import __version__


class BaseTelemetryGenerator:
    """
    Abstract base for emitters mapping GenAI types -> OpenTelemetry.
    """

    def start(self, invocation: LLMInvocation) -> None:
        raise NotImplementedError

    def finish(self, invocation: LLMInvocation) -> None:
        raise NotImplementedError

    def error(self, error: Error, invocation: LLMInvocation) -> None:
        raise NotImplementedError


class SpanGenerator(BaseTelemetryGenerator):
    """
    Generates only spans.
    """

    def __init__(
        self,
        **kwargs: Any,
    ):
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)

    def start(self, invocation: LLMInvocation):
        # Create a span and attach it as current; keep the token to detach later
        span = self._tracer.start_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}",
            kind=SpanKind.CLIENT,
        )
        invocation.span = span
        invocation.context_token = otel_context.attach(
            set_span_in_context(span)
        )

    def finish(self, invocation: LLMInvocation):
        if invocation.context_token is None or invocation.span is None:
            return

        _apply_finish_attributes(invocation.span, invocation)
        # Detach context and end span
        otel_context.detach(invocation.context_token)
        invocation.span.end()

    def error(self, error: Error, invocation: LLMInvocation):
        if invocation.context_token is None or invocation.span is None:
            return

        _apply_error_attributes(invocation.span, error)
        # Detach context and end span
        otel_context.detach(invocation.context_token)
        invocation.span.end()
        return
