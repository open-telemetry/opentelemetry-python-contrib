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

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkExtension,
)
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_STOP_SEQUENCES,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_REQUEST_TOP_P,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_SYSTEM,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    GenAiOperationNameValues,
    GenAiSystemValues,
)
from opentelemetry.trace.span import Span

_logger = logging.getLogger(__name__)

_MODEL_ID_KEY: str = "modelId"


class _BedrockRuntimeExtension(_AwsSdkExtension):
    """
    This class is an extension for <a
    href="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Amazon_Bedrock_Runtime.html">
    Amazon Bedrock Runtime</a>.
    """

    def extract_attributes(self, attributes: _AttributeMapT):
        attributes[GEN_AI_SYSTEM] = GenAiSystemValues.AWS_BEDROCK.value

        model_id = self._call_context.params.get(_MODEL_ID_KEY)
        if model_id:
            attributes[GEN_AI_REQUEST_MODEL] = model_id

            # FIXME: add other model patterns
            text_model_patterns = ["amazon.titan-text", "anthropic.claude"]
            if any(pattern in model_id for pattern in text_model_patterns):
                attributes[GEN_AI_OPERATION_NAME] = (
                    GenAiOperationNameValues.CHAT.value
                )

            if inference_config := self._call_context.params.get(
                "inferenceConfig"
            ):
                self._set_if_not_none(
                    attributes,
                    GEN_AI_REQUEST_TEMPERATURE,
                    inference_config.get("temperature"),
                )
                self._set_if_not_none(
                    attributes,
                    GEN_AI_REQUEST_TOP_P,
                    inference_config.get("topP"),
                )
                self._set_if_not_none(
                    attributes,
                    GEN_AI_REQUEST_MAX_TOKENS,
                    inference_config.get("maxTokens"),
                )
                self._set_if_not_none(
                    attributes,
                    GEN_AI_REQUEST_STOP_SEQUENCES,
                    inference_config.get("stopSequences"),
                )

    @staticmethod
    def _set_if_not_none(attributes, key, value):
        if value is not None:
            attributes[key] = value

    def before_service_call(self, span: Span):
        if not span.is_recording():
            return

        operation_name = span.attributes.get(GEN_AI_OPERATION_NAME, "")
        request_model = span.attributes.get(GEN_AI_REQUEST_MODEL, "")
        # avoid setting to an empty string if are not available
        if operation_name and request_model:
            span.update_name(f"{operation_name} {request_model}")

    def on_success(self, span: Span, result: dict[str, Any]):
        model_id = self._call_context.params.get(_MODEL_ID_KEY)

        if not model_id:
            return

        if usage := result.get("usage"):
            if input_tokens := usage.get("inputTokens"):
                span.set_attribute(
                    GEN_AI_USAGE_INPUT_TOKENS,
                    input_tokens,
                )
            if output_tokens := usage.get("outputTokens"):
                span.set_attribute(
                    GEN_AI_USAGE_OUTPUT_TOKENS,
                    output_tokens,
                )

        if stop_reason := result.get("stopReason"):
            span.set_attribute(
                GEN_AI_RESPONSE_FINISH_REASONS,
                [stop_reason],
            )
