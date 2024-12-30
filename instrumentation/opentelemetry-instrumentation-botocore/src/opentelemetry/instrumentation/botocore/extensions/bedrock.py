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

import io
import json
import logging
import math
from typing import Any

from botocore.response import StreamingBody

from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkExtension,
)
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
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
        attributes[GEN_AI_SYSTEM] = GenAiSystemValues.AWS_BEDROCK
        attributes[GEN_AI_OPERATION_NAME] = GenAiOperationNameValues.CHAT

        model_id = self._call_context.params.get(_MODEL_ID_KEY)
        if model_id:
            attributes[GEN_AI_REQUEST_MODEL] = model_id

            # Get the request body if it exists
            body = self._call_context.params.get("body")
            if body:
                try:
                    request_body = json.loads(body)

                    if "amazon.titan" in model_id:
                        self._extract_titan_attributes(
                            attributes, request_body
                        )
                    if "amazon.nova" in model_id:
                        self._extract_nova_attributes(attributes, request_body)
                    elif "anthropic.claude" in model_id:
                        self._extract_claude_attributes(
                            attributes, request_body
                        )
                    elif "meta.llama" in model_id:
                        self._extract_llama_attributes(
                            attributes, request_body
                        )
                    elif "cohere.command" in model_id:
                        self._extract_cohere_attributes(
                            attributes, request_body
                        )
                    elif "ai21.jamba" in model_id:
                        self._extract_ai21_attributes(attributes, request_body)
                    elif "mistral" in model_id:
                        self._extract_mistral_attributes(
                            attributes, request_body
                        )

                except json.JSONDecodeError:
                    _logger.debug("Error: Unable to parse the body as JSON")

    def _extract_titan_attributes(self, attributes, request_body):
        config = request_body.get("textGenerationConfig", {})
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TEMPERATURE, config.get("temperature")
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, config.get("topP")
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_MAX_TOKENS, config.get("maxTokenCount")
        )

    def _extract_nova_attributes(self, attributes, request_body):
        config = request_body.get("inferenceConfig", {})
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TEMPERATURE, config.get("temperature")
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, config.get("top_p")
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_MAX_TOKENS, config.get("max_new_tokens")
        )

    def _extract_claude_attributes(self, attributes, request_body):
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_MAX_TOKENS,
            request_body.get("max_tokens"),
        )
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_TEMPERATURE,
            request_body.get("temperature"),
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, request_body.get("top_p")
        )

    def _extract_cohere_attributes(self, attributes, request_body):
        prompt = request_body.get("message")
        if prompt:
            attributes[GEN_AI_USAGE_INPUT_TOKENS] = math.ceil(len(prompt) / 6)
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_MAX_TOKENS,
            request_body.get("max_tokens"),
        )
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_TEMPERATURE,
            request_body.get("temperature"),
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, request_body.get("p")
        )

    def _extract_ai21_attributes(self, attributes, request_body):
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_MAX_TOKENS,
            request_body.get("max_tokens"),
        )
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_TEMPERATURE,
            request_body.get("temperature"),
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, request_body.get("top_p")
        )

    def _extract_llama_attributes(self, attributes, request_body):
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_MAX_TOKENS,
            request_body.get("max_gen_len"),
        )
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_TEMPERATURE,
            request_body.get("temperature"),
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, request_body.get("top_p")
        )

    def _extract_mistral_attributes(self, attributes, request_body):
        prompt = request_body.get("prompt")
        if prompt:
            attributes[GEN_AI_USAGE_INPUT_TOKENS] = math.ceil(len(prompt) / 6)
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_MAX_TOKENS,
            request_body.get("max_tokens"),
        )
        self._set_if_not_none(
            attributes,
            GEN_AI_REQUEST_TEMPERATURE,
            request_body.get("temperature"),
        )
        self._set_if_not_none(
            attributes, GEN_AI_REQUEST_TOP_P, request_body.get("top_p")
        )

    @staticmethod
    def _set_if_not_none(attributes, key, value):
        if value is not None:
            attributes[key] = value

    # pylint: disable=too-many-branches
    def on_success(self, span: Span, result: dict[str, Any]):
        model_id = self._call_context.params.get(_MODEL_ID_KEY)

        if not model_id:
            return

        if "body" in result and isinstance(result["body"], StreamingBody):
            original_body = None
            try:
                original_body = result["body"]
                body_content = original_body.read()

                # Use one stream for telemetry
                stream = io.BytesIO(body_content)
                telemetry_content = stream.read()
                response_body = json.loads(telemetry_content.decode("utf-8"))
                if "amazon.titan" in model_id:
                    self._handle_amazon_titan_response(span, response_body)
                if "amazon.nova" in model_id:
                    self._handle_amazon_nova_response(span, response_body)
                elif "anthropic.claude" in model_id:
                    self._handle_anthropic_claude_response(span, response_body)
                elif "meta.llama" in model_id:
                    self._handle_meta_llama_response(span, response_body)
                elif "cohere.command" in model_id:
                    self._handle_cohere_command_response(span, response_body)
                elif "ai21.jamba" in model_id:
                    self._handle_ai21_jamba_response(span, response_body)
                elif "mistral" in model_id:
                    self._handle_mistral_mistral_response(span, response_body)
                # Replenish stream for downstream application use
                new_stream = io.BytesIO(body_content)
                result["body"] = StreamingBody(new_stream, len(body_content))

            except json.JSONDecodeError:
                _logger.debug(
                    "Error: Unable to parse the response body as JSON"
                )
            except Exception as e:  # pylint: disable=broad-exception-caught, invalid-name
                _logger.debug("Error processing response: %s", e)
            finally:
                if original_body is not None:
                    original_body.close()

    # pylint: disable=no-self-use
    def _handle_amazon_titan_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        if "inputTextTokenCount" in response_body:
            span.set_attribute(
                GEN_AI_USAGE_INPUT_TOKENS, response_body["inputTextTokenCount"]
            )
            if "results" in response_body and response_body["results"]:
                result = response_body["results"][0]
                if "tokenCount" in result:
                    span.set_attribute(
                        GEN_AI_USAGE_OUTPUT_TOKENS, result["tokenCount"]
                    )
                if "completionReason" in result:
                    span.set_attribute(
                        GEN_AI_RESPONSE_FINISH_REASONS,
                        [result["completionReason"]],
                    )

    # pylint: disable=no-self-use
    def _handle_amazon_nova_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        if "usage" in response_body:
            usage = response_body["usage"]
            if "inputTokens" in usage:
                span.set_attribute(
                    GEN_AI_USAGE_INPUT_TOKENS, usage["inputTokens"]
                )
            if "outputTokens" in usage:
                span.set_attribute(
                    GEN_AI_USAGE_OUTPUT_TOKENS, usage["outputTokens"]
                )
        if "stopReason" in response_body:
            span.set_attribute(
                GEN_AI_RESPONSE_FINISH_REASONS, [response_body["stopReason"]]
            )

    # pylint: disable=no-self-use
    def _handle_anthropic_claude_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        if "usage" in response_body:
            usage = response_body["usage"]
            if "input_tokens" in usage:
                span.set_attribute(
                    GEN_AI_USAGE_INPUT_TOKENS, usage["input_tokens"]
                )
            if "output_tokens" in usage:
                span.set_attribute(
                    GEN_AI_USAGE_OUTPUT_TOKENS, usage["output_tokens"]
                )
        if "stop_reason" in response_body:
            span.set_attribute(
                GEN_AI_RESPONSE_FINISH_REASONS, [response_body["stop_reason"]]
            )

    # pylint: disable=no-self-use
    def _handle_cohere_command_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        # Output tokens: Approximate from the response text
        if "text" in response_body:
            span.set_attribute(
                GEN_AI_USAGE_OUTPUT_TOKENS,
                math.ceil(len(response_body["text"]) / 6),
            )
        if "finish_reason" in response_body:
            span.set_attribute(
                GEN_AI_RESPONSE_FINISH_REASONS,
                [response_body["finish_reason"]],
            )

    # pylint: disable=no-self-use
    def _handle_ai21_jamba_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        if "usage" in response_body:
            usage = response_body["usage"]
            if "prompt_tokens" in usage:
                span.set_attribute(
                    GEN_AI_USAGE_INPUT_TOKENS, usage["prompt_tokens"]
                )
            if "completion_tokens" in usage:
                span.set_attribute(
                    GEN_AI_USAGE_OUTPUT_TOKENS, usage["completion_tokens"]
                )
        if "choices" in response_body:
            choices = response_body["choices"][0]
            if "finish_reason" in choices:
                span.set_attribute(
                    GEN_AI_RESPONSE_FINISH_REASONS, [choices["finish_reason"]]
                )

    # pylint: disable=no-self-use
    def _handle_meta_llama_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        if "prompt_token_count" in response_body:
            span.set_attribute(
                GEN_AI_USAGE_INPUT_TOKENS, response_body["prompt_token_count"]
            )
        if "generation_token_count" in response_body:
            span.set_attribute(
                GEN_AI_USAGE_OUTPUT_TOKENS,
                response_body["generation_token_count"],
            )
        if "stop_reason" in response_body:
            span.set_attribute(
                GEN_AI_RESPONSE_FINISH_REASONS, [response_body["stop_reason"]]
            )

    # pylint: disable=no-self-use
    def _handle_mistral_mistral_response(
        self, span: Span, response_body: dict[str, Any]
    ):
        if "outputs" in response_body:
            outputs = response_body["outputs"][0]
            if "text" in outputs:
                span.set_attribute(
                    GEN_AI_USAGE_OUTPUT_TOKENS,
                    math.ceil(len(outputs["text"]) / 6),
                )
        if "stop_reason" in outputs:
            span.set_attribute(
                GEN_AI_RESPONSE_FINISH_REASONS, [outputs["stop_reason"]]
            )
