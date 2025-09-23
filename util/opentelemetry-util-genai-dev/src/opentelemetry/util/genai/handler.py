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
Telemetry handler for GenAI invocations.

This module exposes the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data (spans and related attributes).
It supports starting, stopping, and failing LLM invocations.

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage:
    handler = get_telemetry_handler()

    # Create an invocation object with your request data
    invocation = LLMInvocation(
        request_model="my-model",
        input_messages=[...],
        provider="my-provider",
        attributes={"custom": "attr"},
    )

    # Start the invocation (opens a span)
    handler.start_llm(invocation)

    # Populate outputs and any additional attributes, then stop (closes the span)
    invocation.output_messages = [...]
    invocation.attributes.update({"more": "attrs"})
    handler.stop_llm(invocation)

    # Or, in case of error
    # handler.fail_llm(invocation, Error(type="...", message="..."))
"""

import os
import time
from typing import Any, Dict, Optional

from opentelemetry import _events as _otel_events
from opentelemetry import metrics as _metrics
from opentelemetry import trace as _trace_mod
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import Link, get_tracer

# Side-effect import registers builtin evaluators
from opentelemetry.util.genai import (
    evaluators as _genai_evaluators,  # noqa: F401
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
    OTEL_INSTRUMENTATION_GENAI_GENERATOR,
)
from opentelemetry.util.genai.evaluators.registry import (
    get_evaluator,
    register_evaluator,
)
from opentelemetry.util.genai.generators import SpanGenerator
from opentelemetry.util.genai.generators.span_metric_event_generator import (
    SpanMetricEventGenerator,
)
from opentelemetry.util.genai.generators.span_metric_generator import (
    SpanMetricGenerator,
)
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    EvaluationResult,
    LLMInvocation,
)
from opentelemetry.util.genai.utils import get_content_capturing_mode
from opentelemetry.util.genai.version import __version__


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(self, **kwargs: Any):
        tracer_provider = kwargs.get("tracer_provider")
        # Store provider reference for later identity comparison (test isolation)
        from opentelemetry import trace as _trace_mod_local

        self._tracer_provider_ref = (
            tracer_provider or _trace_mod_local.get_tracer_provider()
        )
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )
        self._event_logger = _otel_events.get_event_logger(__name__)
        meter_provider = kwargs.get("meter_provider")
        self._meter_provider = meter_provider  # store for flushing in tests
        if meter_provider is not None:
            meter = meter_provider.get_meter(__name__)
        else:
            meter = _metrics.get_meter(__name__)
        # Single histogram for all evaluation scores (name stable across metrics)
        self._evaluation_histogram = meter.create_histogram(
            name="gen_ai.evaluation.score",
            unit="1",
            description="Scores produced by GenAI evaluators in [0,1] when applicable",
        )

        # Generator selection via env var (experimental)
        gen_choice = (
            os.environ.get(OTEL_INSTRUMENTATION_GENAI_GENERATOR, "span")
            .strip()
            .lower()
        )
        self._generator_kind = gen_choice
        # Decide capture_content AFTER knowing generator kind so EVENT_ONLY works for event flavor.
        capture_content = False
        try:
            mode = get_content_capturing_mode()
            if gen_choice == "span_metric_event":
                capture_content = mode in (
                    ContentCapturingMode.EVENT_ONLY,
                    ContentCapturingMode.SPAN_AND_EVENT,
                )
            else:  # span / span_metric
                capture_content = mode in (
                    ContentCapturingMode.SPAN_ONLY,
                    ContentCapturingMode.SPAN_AND_EVENT,
                )
        except Exception:
            capture_content = False
        if gen_choice == "span_metric_event":
            self._generator = SpanMetricEventGenerator(
                tracer=self._tracer,
                capture_content=capture_content,
                meter=meter,
            )
        elif gen_choice == "span_metric":
            self._generator = SpanMetricGenerator(
                tracer=self._tracer,
                capture_content=capture_content,
                meter=meter,
            )
        else:  # default fallback spans only
            self._generator = SpanGenerator(
                tracer=self._tracer, capture_content=capture_content
            )

    def _refresh_capture_content(
        self,
    ):  # re-evaluate env each start in case singleton created before patching
        try:
            mode = get_content_capturing_mode()
            if self._generator_kind == "span_metric_event":
                new_value = mode in (
                    ContentCapturingMode.EVENT_ONLY,
                    ContentCapturingMode.SPAN_AND_EVENT,
                )
            else:
                new_value = mode in (
                    ContentCapturingMode.SPAN_ONLY,
                    ContentCapturingMode.SPAN_AND_EVENT,
                )
            # Generators use _capture_content attribute; ignore if absent
            if hasattr(self._generator, "_capture_content"):
                self._generator._capture_content = new_value  # type: ignore[attr-defined]
        except Exception:
            pass

    def start_llm(
        self,
        invocation: LLMInvocation,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry."""
        self._refresh_capture_content()
        self._generator.start(invocation)
        return invocation

    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:
        """Finalize an LLM invocation successfully and end its span."""
        invocation.end_time = time.time()
        self._generator.finish(invocation)
        # Force flush metrics if a custom provider with force_flush is present
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover - defensive
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return invocation

    def fail_llm(
        self, invocation: LLMInvocation, error: Error
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status."""
        invocation.end_time = time.time()
        self._generator.error(error, invocation)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return invocation

    def evaluate_llm(
        self,
        invocation: LLMInvocation,
        evaluators: Optional[list[str]] = None,
    ) -> list[EvaluationResult]:
        """Run registered evaluators against a completed LLMInvocation.

        Executes evaluator backends, records scores to a unified histogram
        (gen_ai.evaluation.score), emits a gen_ai.evaluations event, and optionally
        creates evaluation spans controlled by OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE
        (off | aggregated | per_metric).

        Evaluation enablement is controlled by the environment variable
        OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE. If not enabled, this
        returns an empty list.

        Args:
            invocation: The LLMInvocation that has been finished (stop_llm or fail_llm).
            evaluators: Optional explicit list of evaluator names. If None, falls back
                to OTEL_INSTRUMENTATION_GENAI_EVALUATORS (comma-separated). If still
                empty, returns [] immediately.

        Returns:
            A list of EvaluationResult objects (possibly empty).
        """
        enabled_val = os.environ.get(
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE, "false"
        ).lower()
        if enabled_val not in ("true", "1", "yes"):  # disabled
            return []

        if evaluators is None:
            env_names = os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_EVALUATORS, ""
            ).strip()
            if env_names:
                evaluators = [
                    n.strip() for n in env_names.split(",") if n.strip()
                ]
            else:
                evaluators = []
        if not evaluators:
            return []

        results: list[EvaluationResult] = []
        # Ensure invocation end_time is set (user might have forgotten to call stop_llm)
        if invocation.end_time is None:
            invocation.end_time = time.time()

        for name in evaluators:
            evaluator = None
            try:
                evaluator = get_evaluator(name)
            except Exception:
                import importlib

                evaluator = None
                lower = name.lower()
                # Built-in evaluators
                if lower in {"length", "sentiment"}:
                    try:  # pragma: no cover
                        mod = importlib.import_module(
                            "opentelemetry.util.genai.evaluators.builtins"
                        )
                        if hasattr(mod, "LengthEvaluator"):
                            register_evaluator(
                                "length", lambda: mod.LengthEvaluator()
                            )
                        if hasattr(mod, "SentimentEvaluator"):
                            register_evaluator(
                                "sentiment", lambda: mod.SentimentEvaluator()
                            )
                        evaluator = get_evaluator(name)
                    except Exception:
                        evaluator = None
                # External DeepEval integration
                if lower == "deepeval" and evaluator is None:
                    try:
                        # Load external deepeval integration from utils-genai-evals-deepeval package
                        ext_mod = importlib.import_module(
                            "opentelemetry.util.genai.evals.deepeval"
                        )
                        if hasattr(ext_mod, "DeepEvalEvaluator"):
                            # factory captures handler's event_logger and tracer
                            register_evaluator(
                                "deepeval",
                                lambda: ext_mod.DeepEvalEvaluator(
                                    self._event_logger, self._tracer
                                ),
                            )
                            evaluator = get_evaluator(name)
                    except ImportError:
                        evaluator = None
                if evaluator is None:
                    results.append(
                        EvaluationResult(
                            metric_name=name,
                            error=Error(
                                message=f"Unknown evaluator: {name}",
                                type=LookupError,
                            ),
                        )
                    )
                    continue
            try:
                eval_out = evaluator.evaluate(invocation)
                if isinstance(eval_out, EvaluationResult):
                    payload = [eval_out]
                elif isinstance(eval_out, list):
                    payload = eval_out
                else:
                    payload = [
                        EvaluationResult(
                            metric_name=name,
                            error=Error(
                                message="Evaluator returned unsupported type",
                                type=TypeError,
                            ),
                        )
                    ]
                for item in payload:
                    if isinstance(item, EvaluationResult):
                        results.append(item)
                    else:
                        results.append(
                            EvaluationResult(
                                metric_name=name,
                                error=Error(
                                    message="Evaluator returned non-EvaluationResult item",
                                    type=TypeError,
                                ),
                            )
                        )
            except Exception as exc:  # evaluator runtime error
                results.append(
                    EvaluationResult(
                        metric_name=name,
                        error=Error(message=str(exc), type=type(exc)),
                    )
                )
        # Emit metrics & event
        if results:
            evaluation_items: list[Dict[str, Any]] = []
            for res in results:
                attrs: Dict[str, Any] = {
                    "gen_ai.operation.name": "evaluation",
                    "gen_ai.evaluation.name": res.metric_name,
                    "gen_ai.request.model": invocation.request_model,
                }
                if invocation.provider:
                    attrs["gen_ai.provider.name"] = invocation.provider
                if res.label is not None:
                    attrs["gen_ai.evaluation.score.label"] = res.label
                if res.error is not None:
                    attrs["error.type"] = res.error.type.__qualname__
                # Record metric if score present and numeric
                if isinstance(res.score, (int, float)):
                    self._evaluation_histogram.record(
                        res.score,
                        attributes={
                            k: v for k, v in attrs.items() if v is not None
                        },
                    )
                # Build event body item
                item = {
                    "gen_ai.evaluation.name": res.metric_name,
                }
                if isinstance(res.score, (int, float)):
                    item["gen_ai.evaluation.score.value"] = (
                        res.score
                    )  # value is numeric; acceptable
                if res.label is not None:
                    item["gen_ai.evaluation.score.label"] = res.label
                if res.explanation:
                    item["gen_ai.evaluation.explanation"] = res.explanation
                if res.error is not None:
                    item["error.type"] = res.error.type.__qualname__
                    item["error.message"] = res.error.message
                # include custom attributes from evaluator result
                for k, v in res.attributes.items():
                    item[k] = v
                evaluation_items.append(item)
            if evaluation_items:
                event_attrs = {
                    "gen_ai.operation.name": "evaluation",
                    "gen_ai.request.model": invocation.request_model,
                }
                if invocation.provider:
                    event_attrs["gen_ai.provider.name"] = invocation.provider
                if invocation.response_id:
                    event_attrs["gen_ai.response.id"] = invocation.response_id
                event_body = {"evaluations": evaluation_items}
                try:
                    self._event_logger.emit(
                        _otel_events.Event(
                            name="gen_ai.evaluations",
                            attributes=event_attrs,
                            body=event_body,
                            # Link to invocation span if available
                            span_id=invocation.span.get_span_context().span_id
                            if invocation.span
                            else None,
                            trace_id=invocation.span.get_span_context().trace_id
                            if invocation.span
                            else None,
                        )
                    )
                except Exception:  # pragma: no cover - defensive
                    pass

                # Create evaluation spans based on span mode
                span_mode = os.environ.get(
                    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE, "off"
                ).lower()
                if span_mode not in ("off", "aggregated", "per_metric"):
                    span_mode = "off"
                parent_link = None
                if invocation.span:
                    parent_link = Link(
                        invocation.span.get_span_context(),
                        attributes={"gen_ai.operation.name": "chat"},
                    )
                if span_mode == "aggregated":
                    with self._tracer.start_as_current_span(
                        "evaluation",
                        links=[parent_link] if parent_link else None,
                    ) as span:
                        span.set_attribute(
                            "gen_ai.operation.name", "evaluation"
                        )
                        span.set_attribute(
                            "gen_ai.request.model", invocation.request_model
                        )
                        if invocation.provider:
                            span.set_attribute(
                                "gen_ai.provider.name", invocation.provider
                            )
                        span.set_attribute(
                            "gen_ai.evaluation.count", len(evaluation_items)
                        )
                        # Aggregate score stats (only numeric)
                        numeric_scores = [
                            it.get("gen_ai.evaluation.score.value")
                            for it in evaluation_items
                            if isinstance(
                                it.get("gen_ai.evaluation.score.value"),
                                (int, float),
                            )
                        ]
                        if numeric_scores:
                            span.set_attribute(
                                "gen_ai.evaluation.score.min",
                                min(numeric_scores),
                            )
                            span.set_attribute(
                                "gen_ai.evaluation.score.max",
                                max(numeric_scores),
                            )
                            span.set_attribute(
                                "gen_ai.evaluation.score.avg",
                                sum(numeric_scores) / len(numeric_scores),
                            )
                        # Optionally store names list
                        span.set_attribute(
                            "gen_ai.evaluation.names",
                            [
                                it["gen_ai.evaluation.name"]
                                for it in evaluation_items
                            ],
                        )
                elif span_mode == "per_metric":
                    for item in evaluation_items:
                        name = item.get("gen_ai.evaluation.name", "unknown")
                        span_name = f"evaluation.{name}"
                        with self._tracer.start_as_current_span(
                            span_name,
                            links=[parent_link] if parent_link else None,
                        ) as span:
                            span.set_attribute(
                                "gen_ai.operation.name", "evaluation"
                            )
                            span.set_attribute("gen_ai.evaluation.name", name)
                            span.set_attribute(
                                "gen_ai.request.model",
                                invocation.request_model,
                            )
                            if invocation.provider:
                                span.set_attribute(
                                    "gen_ai.provider.name", invocation.provider
                                )
                            if "gen_ai.evaluation.score.value" in item:
                                span.set_attribute(
                                    "gen_ai.evaluation.score.value",
                                    item["gen_ai.evaluation.score.value"],
                                )
                            if "gen_ai.evaluation.score.label" in item:
                                span.set_attribute(
                                    "gen_ai.evaluation.score.label",
                                    item["gen_ai.evaluation.score.label"],
                                )
                            if "error.type" in item:
                                span.set_attribute(
                                    "error.type", item["error.type"]
                                )
        return results


def get_telemetry_handler(**kwargs: Any) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance. If the global tracer provider
    has changed since the handler was created, a new handler is instantiated so that
    spans are recorded with the active provider (important for test isolation).
    """
    handler: Optional[TelemetryHandler] = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    current_provider = _trace_mod.get_tracer_provider()
    recreate = False
    if handler is not None:
        # Recreate if provider changed or handler lacks provider reference (older instance)
        if not hasattr(handler, "_tracer_provider_ref"):
            recreate = True
        elif handler._tracer_provider_ref is not current_provider:  # type: ignore[attr-defined]
            recreate = True
    if handler is None or recreate:
        handler = TelemetryHandler(**kwargs)
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
