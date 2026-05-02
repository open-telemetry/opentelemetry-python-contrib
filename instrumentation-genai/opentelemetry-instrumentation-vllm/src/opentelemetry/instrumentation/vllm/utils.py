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

"""Utility functions to extract telemetry attributes from vLLM objects."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode

VLLM_SYSTEM = "vllm"
# TODO: "vllm" is not yet a registered value for gen_ai.system in OpenTelemetry
# semantic conventions. A PR needs to be opened at
# https://github.com/open-telemetry/semantic-conventions to register it.
# See the current gen_ai attribute definitions at:
# https://opentelemetry.io/docs/specs/semconv/attributes/gen-ai/


def get_span_name(operation_name: str, model: Optional[str]) -> str:
    if model:
        return f"{operation_name} {model}"
    return operation_name


def get_common_attributes(
    operation_name: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    attributes: Dict[str, Any] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: VLLM_SYSTEM,
    }
    if model:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = model
    return attributes


def get_request_attributes(
    operation_name: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
) -> Dict[str, Any]:
    """Build span attributes for a vLLM request."""
    attributes = get_common_attributes(operation_name, model)

    if temperature is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] = temperature
    if max_tokens is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] = max_tokens
    if top_p is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] = top_p
    if top_k is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_K] = top_k
    if frequency_penalty is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] = (
            frequency_penalty
        )
    if presence_penalty is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] = (
            presence_penalty
        )

    return attributes


def extract_sampling_params(sampling_params: Any) -> Dict[str, Any]:
    """Extract relevant parameters from a vLLM SamplingParams object."""
    params: Dict[str, Any] = {}
    if sampling_params is None:
        return params

    for attr, key in [
        ("temperature", "temperature"),
        ("max_tokens", "max_tokens"),
        ("top_p", "top_p"),
        ("top_k", "top_k"),
        ("frequency_penalty", "frequency_penalty"),
        ("presence_penalty", "presence_penalty"),
    ]:
        val = getattr(sampling_params, attr, None)
        if val is not None:
            params[key] = val

    return params


def extract_token_counts(
    request_output: Any,
) -> Tuple[Optional[int], Optional[int]]:
    """Extract input and output token counts from a vLLM RequestOutput.

    Returns (prompt_tokens, completion_tokens).
    """
    prompt_tokens = None
    completion_tokens = None

    # vLLM's RequestOutput has prompt_token_ids and outputs[i].token_ids
    prompt_token_ids = getattr(request_output, "prompt_token_ids", None)
    if prompt_token_ids is not None:
        prompt_tokens = len(prompt_token_ids)

    outputs = getattr(request_output, "outputs", None)
    if outputs:
        completion_tokens = 0
        for output in outputs:
            token_ids = getattr(output, "token_ids", None)
            if token_ids is not None:
                completion_tokens += len(token_ids)

    return prompt_tokens, completion_tokens


def extract_finish_reasons(request_output: Any) -> Optional[List[str]]:
    """Extract finish reasons from a vLLM RequestOutput."""
    outputs = getattr(request_output, "outputs", None)
    if not outputs:
        return None

    reasons = []
    for output in outputs:
        reason = getattr(output, "finish_reason", None)
        if reason is not None:
            reasons.append(str(reason))
        else:
            reasons.append("unknown")
    return reasons


def extract_response_model(request_output: Any) -> Optional[str]:
    """Extract model name from vLLM's RequestOutput if available."""
    return getattr(request_output, "model", None)


def extract_server_metrics(
    request_output: Any,
) -> Tuple[Optional[float], Optional[float]]:
    """Extract server-side timing metrics from vLLM RequestOutput.

    vLLM's RequestOutput.metrics contains (among others):
      - first_token_latency — time from request arrival to first token (TTFT)
      - mean_time_per_output_token — average inter-token latency (TPOT)

    TTFT and TPOT measure fundamentally different things:
      - TTFT captures how long the user waits before seeing any output.
      - TPOT captures the average time between consecutive output tokens,
        reflecting sustained generation throughput.

    Returns (ttft, tpot) in seconds or (None, None) if unavailable.
    """
    metrics = getattr(request_output, "metrics", None)
    if metrics is None:
        return None, None

    ttft = None
    tpot = None

    # TTFT: time from request arrival to first generated token
    if hasattr(metrics, "first_token_latency"):
        ttft = metrics.first_token_latency
    elif isinstance(metrics, dict):
        ttft = metrics.get("first_token_latency")

    # TPOT: mean time between consecutive output tokens
    if hasattr(metrics, "mean_time_per_output_token"):
        tpot = metrics.mean_time_per_output_token
    elif isinstance(metrics, dict):
        tpot = metrics.get("mean_time_per_output_token")

    return ttft, tpot


def set_response_attributes(
    span: Span,
    request_output: Any,
) -> None:
    """Set span attributes from a vLLM response."""
    response_model = extract_response_model(request_output)
    if response_model:
        span.set_attribute(
            GenAIAttributes.GEN_AI_RESPONSE_MODEL, response_model
        )

    response_id = getattr(request_output, "request_id", None)
    if response_id:
        span.set_attribute(GenAIAttributes.GEN_AI_RESPONSE_ID, response_id)

    finish_reasons = extract_finish_reasons(request_output)
    if finish_reasons:
        span.set_attribute(
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
        )

    prompt_tokens, completion_tokens = extract_token_counts(request_output)
    if prompt_tokens is not None:
        span.set_attribute(
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens
        )
    if completion_tokens is not None:
        span.set_attribute(
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens
        )


def handle_span_exception(span: Span, error: BaseException) -> None:
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute("error.type", type(error).__qualname__)
    span.end()
