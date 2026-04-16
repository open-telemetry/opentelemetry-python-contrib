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

"""Patch functions for vLLM instrumentation."""

from __future__ import annotations

from timeit import default_timer
from typing import Any, List, Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer

from .instruments import Instruments
from .utils import (
    VLLM_SYSTEM,
    extract_finish_reasons,
    extract_sampling_params,
    extract_server_metrics,
    extract_token_counts,
    get_request_attributes,
    get_span_name,
    handle_span_exception,
    set_response_attributes,
)


def _record_metrics(
    instruments: Instruments,
    request_output: Any,
    duration: float,
    operation_name: str,
    model: Optional[str],
) -> None:
    """Record all metrics for a completed vLLM request."""
    metric_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: VLLM_SYSTEM,
    }
    if model:
        metric_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = model

    response_model = getattr(request_output, "model", None)
    if response_model:
        metric_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = (
            response_model
        )

    # Operation duration -- we only record this once via the client
    # operation duration histogram. For local/offline inference
    # (vllm.LLM), client and server durations are identical so there
    # is no need to record both. If we later support vLLM's
    # AsyncLLMEngine (remote serving mode), the
    # server_request_duration can be re-enabled to capture the
    # server-side portion independently.
    instruments.client_operation_duration_histogram.record(
        duration, attributes=metric_attributes
    )

    # Server-side TTFT and TPOT
    ttft, tpot = extract_server_metrics(request_output)
    if ttft is not None:
        instruments.server_ttft_histogram.record(
            ttft, attributes=metric_attributes
        )
    if tpot is not None:
        instruments.server_tpot_histogram.record(
            tpot, attributes=metric_attributes
        )

    # Token usage
    prompt_tokens, completion_tokens = extract_token_counts(request_output)
    if prompt_tokens is not None:
        token_attrs = {
            **metric_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
        }
        instruments.client_token_usage_histogram.record(
            prompt_tokens, attributes=token_attrs
        )
    if completion_tokens is not None:
        token_attrs = {
            **metric_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
        }
        instruments.client_token_usage_histogram.record(
            completion_tokens, attributes=token_attrs
        )


def _process_results(
    results: Any,
    span: Any,
    instruments: Instruments,
    duration: float,
    operation_name: str,
    model: Optional[str],
) -> None:
    """Process results from vLLM generate/chat, setting attributes and recording metrics."""
    if results:
        # vLLM returns a list of RequestOutput
        if isinstance(results, list) and len(results) > 0:
            first_result = results[0]
        else:
            first_result = results

        set_response_attributes(span, first_result)
        _record_metrics(
            instruments, first_result, duration, operation_name, model
        )


def _get_model_from_instance(instance: Any) -> Optional[str]:
    """Try to extract the model name from a vLLM LLM instance."""
    # vLLM LLM class stores model in llm_engine.model_config.model
    engine = getattr(instance, "llm_engine", None)
    if engine:
        model_config = getattr(engine, "model_config", None)
        if model_config:
            return getattr(model_config, "model", None)
    # Fallback: some versions store it directly
    return getattr(instance, "model", None)


def generate_wrapper(tracer: Tracer, instruments: Instruments):
    """Create a wrapper for vLLM LLM.generate()."""
    operation_name = (
        GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
    )

    def traced_method(wrapped, instance, args, kwargs):
        model = _get_model_from_instance(instance)

        # Extract sampling params from args/kwargs
        sampling_params = kwargs.get("sampling_params") or (
            args[1] if len(args) > 1 else None
        )
        sp_dict = extract_sampling_params(sampling_params)

        span_attributes = get_request_attributes(
            operation_name=operation_name,
            model=model,
            **sp_dict,
        )

        span_name = get_span_name(operation_name, model)
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            start = default_timer()
            try:
                result = wrapped(*args, **kwargs)
                duration = default_timer() - start
                if span.is_recording():
                    _process_results(
                        result,
                        span,
                        instruments,
                        duration,
                        operation_name,
                        model,
                    )
                span.end()
                return result
            except Exception as error:
                duration = default_timer() - start
                handle_span_exception(span, error)
                raise

    return traced_method


def chat_wrapper(tracer: Tracer, instruments: Instruments):
    """Create a wrapper for vLLM LLM.chat()."""
    operation_name = GenAIAttributes.GenAiOperationNameValues.CHAT.value

    def traced_method(wrapped, instance, args, kwargs):
        model = _get_model_from_instance(instance)

        sampling_params = kwargs.get("sampling_params") or (
            args[1] if len(args) > 1 else None
        )
        sp_dict = extract_sampling_params(sampling_params)

        span_attributes = get_request_attributes(
            operation_name=operation_name,
            model=model,
            **sp_dict,
        )

        span_name = get_span_name(operation_name, model)
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            start = default_timer()
            try:
                result = wrapped(*args, **kwargs)
                duration = default_timer() - start
                if span.is_recording():
                    _process_results(
                        result,
                        span,
                        instruments,
                        duration,
                        operation_name,
                        model,
                    )
                span.end()
                return result
            except Exception as error:
                duration = default_timer() - start
                handle_span_exception(span, error)
                raise

    return traced_method
