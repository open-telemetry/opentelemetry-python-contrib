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

from __future__ import annotations

from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.types import AttributeValue


class EmbeddingInvocation(GenAIInvocation):
    """Represents a single embedding model invocation.

    Use handler.start_embedding(provider) or the handler.embedding(provider)
    context manager rather than constructing this directly.
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        encoding_formats: list[str] | None = None,
        input_tokens: int | None = None,
        dimension_count: int | None = None,
        response_model_name: str | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Use handler.start_embedding(provider) or handler.embedding(provider) instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.EMBEDDINGS.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            operation_name=_operation_name,
            span_name=f"{_operation_name} {request_model}"
            if request_model
            else _operation_name,
            span_kind=SpanKind.CLIENT,
            attributes=attributes,
            metric_attributes=metric_attributes,
        )
        self.provider = provider  # e.g., azure.ai.openai, openai, aws.bedrock
        self.request_model = request_model
        self.server_address = server_address
        self.server_port = server_port
        # encoding_formats can be multi-value -> combinational cardinality risk.
        # Keep on spans/events only.
        self.encoding_formats = encoding_formats
        self.input_tokens = input_tokens
        self.dimension_count = dimension_count
        self.response_model_name = response_model_name
        self._start()

    def _get_metric_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
            (GenAI.GEN_AI_RESPONSE_MODEL, self.response_model_name),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
        )
        attrs: dict[str, AttributeValue] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
        }
        attrs.update(self.metric_attributes)
        return attrs

    def _get_metric_token_counts(self) -> dict[str, int]:
        if self.input_tokens is not None:
            return {GenAI.GenAiTokenTypeValues.INPUT.value: self.input_tokens}
        return {}

    def _apply_finish(self, error: Error | None = None) -> None:
        optional_attrs = (
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
            (GenAI.GEN_AI_EMBEDDINGS_DIMENSION_COUNT, self.dimension_count),
            (GenAI.GEN_AI_REQUEST_ENCODING_FORMATS, self.encoding_formats),
            (GenAI.GEN_AI_RESPONSE_MODEL, self.response_model_name),
            (GenAI.GEN_AI_USAGE_INPUT_TOKENS, self.input_tokens),
        )
        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{
                key: value
                for key, value in optional_attrs
                if value is not None
            },
        }
        if error is not None:
            self._apply_error_attributes(error)
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        # Metrics recorder currently supports InferenceInvocation fields only.
        # No-op until dedicated embedding metric support is added.
