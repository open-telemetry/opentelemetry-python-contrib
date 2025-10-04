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
"""Implementation of the Deepeval evaluator plugin."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import (
    EvaluatorRegistration,
    register_evaluator,
)
from opentelemetry.util.genai.types import (
    AgentInvocation,
    Error,
    EvaluationResult,
    GenAI,
    LLMInvocation,
    Text,
)

_DEFAULT_METRICS: Mapping[str, Sequence[str]] = {
    "LLMInvocation": (
        "bias",
        "toxicity",
        "answer_relevancy",
        "faithfulness",
    ),
    "AgentInvocation": (
        "bias",
        "toxicity",
        "answer_relevancy",
        "faithfulness",
    ),
}


_LOGGER = logging.getLogger(__name__)


# Disable Deepeval's internal telemetry (Posthog/New Relic) by default so that
# it does not emit extra spans or events when running inside the GenAI
# instrumentation stack. Users can re-enable it by explicitly setting
# ``DEEPEVAL_TELEMETRY_OPT_OUT`` to ``0`` before importing this module.
if os.environ.get("DEEPEVAL_TELEMETRY_OPT_OUT") is None:
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"


@dataclass(frozen=True)
class _MetricSpec:
    name: str
    options: Mapping[str, Any]


def _metric_registry() -> Mapping[str, str]:
    # Map normalized metric names to the attribute on deepeval.metrics
    return {
        "bias": "BiasMetric",
        "toxicity": "ToxicityMetric",
        "answer_relevancy": "AnswerRelevancyMetric",
        "faithfulness": "FaithfulnessMetric",
    }


class DeepevalEvaluator(Evaluator):
    """Evaluator using Deepeval as an LLM-as-a-judge backend."""

    def __init__(
        self,
        metrics: Iterable[str] | None = None,
        *,
        invocation_type: str | None = None,
        options: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        super().__init__(
            metrics,
            invocation_type=invocation_type,
            options=options,
        )

    # ---- Defaults -----------------------------------------------------
    def default_metrics_by_type(self) -> Mapping[str, Sequence[str]]:
        return _DEFAULT_METRICS

    def default_metrics(self) -> Sequence[str]:  # pragma: no cover - fallback
        return _DEFAULT_METRICS["LLMInvocation"]

    # ---- Evaluation ---------------------------------------------------
    def evaluate(self, item: GenAI) -> list[EvaluationResult]:
        if isinstance(item, LLMInvocation):
            return list(self._evaluate_llm(item))
        if isinstance(item, AgentInvocation):
            return list(self._evaluate_agent(item))
        return []

    def _evaluate_llm(
        self, invocation: LLMInvocation
    ) -> Sequence[EvaluationResult]:
        return self._evaluate_generic(invocation, "LLMInvocation")

    def _evaluate_agent(
        self, invocation: AgentInvocation
    ) -> Sequence[EvaluationResult]:
        return self._evaluate_generic(invocation, "AgentInvocation")

    def _evaluate_generic(
        self, invocation: GenAI, invocation_type: str
    ) -> Sequence[EvaluationResult]:
        metric_specs = self._build_metric_specs()
        if not metric_specs:
            return []
        test_case = self._build_test_case(invocation, invocation_type)
        if test_case is None:
            return self._error_results(
                "Deepeval requires both input and output text to evaluate",
                ValueError,
            )
        try:
            metrics, skipped_results = self._instantiate_metrics(
                metric_specs, test_case
            )
        except Exception as exc:  # pragma: no cover - defensive
            return self._error_results(str(exc), type(exc))
        if not metrics:
            return skipped_results or self._error_results(
                "No Deepeval metrics available", RuntimeError
            )
        try:
            evaluation = self._run_deepeval(test_case, metrics)
        except (
            Exception
        ) as exc:  # pragma: no cover - dependency/runtime failure
            return [
                *skipped_results,
                *self._error_results(str(exc), type(exc)),
            ]
        return [*skipped_results, *self._convert_results(evaluation)]

    # ---- Helpers ------------------------------------------------------
    def _build_metric_specs(self) -> Sequence[_MetricSpec]:
        specs: list[_MetricSpec] = []
        registry = _metric_registry()
        for name in self.metrics:
            key = (name or "").strip().lower()
            options = self.options.get(name, {})
            if key not in registry:
                specs.append(
                    _MetricSpec(
                        name=name,
                        options={
                            "__error__": f"Unknown Deepeval metric '{name}'",
                        },
                    )
                )
                continue
            parsed_options = {
                opt_key: self._coerce_option(opt_value)
                for opt_key, opt_value in options.items()
            }
            specs.append(_MetricSpec(name=key, options=parsed_options))
        return specs

    def _instantiate_metrics(  # pragma: no cover - exercised via tests
        self, specs: Sequence[_MetricSpec], test_case: Any
    ) -> tuple[Sequence[Any], Sequence[EvaluationResult]]:
        from importlib import import_module

        metrics_module = import_module("deepeval.metrics")
        registry = _metric_registry()
        instances: list[Any] = []
        skipped: list[EvaluationResult] = []
        default_model = self._default_model()
        for spec in specs:
            if "__error__" in spec.options:
                raise ValueError(spec.options["__error__"])
            metric_class_name = registry[spec.name]
            metric_cls = getattr(metrics_module, metric_class_name)
            missing = self._missing_required_params(metric_cls, test_case)
            if missing:
                message = (
                    "Missing required Deepeval test case fields "
                    f"{', '.join(missing)} for metric '{spec.name}'."
                )
                _LOGGER.info(
                    "Skipping Deepeval metric '%s': %s", spec.name, message
                )
                skipped.append(
                    EvaluationResult(
                        metric_name=spec.name,
                        label="skipped",
                        explanation=message,
                        error=Error(message=message, type=ValueError),
                        attributes={
                            "deepeval.error": message,
                            "deepeval.skipped": True,
                            "deepeval.missing_params": missing,
                        },
                    )
                )
                continue
            kwargs = dict(spec.options)
            kwargs.setdefault("include_reason", True)
            if default_model and "model" not in kwargs:
                kwargs["model"] = default_model
            try:
                instances.append(metric_cls(**kwargs))
            except TypeError as exc:
                raise TypeError(
                    f"Failed to instantiate Deepeval metric '{spec.name}': {exc}"
                )
        return instances, skipped

    def _build_test_case(
        self, invocation: GenAI, invocation_type: str
    ) -> Any | None:
        from deepeval.test_case import LLMTestCase

        if isinstance(invocation, LLMInvocation):
            input_text = self._serialize_messages(invocation.input_messages)
            if not input_text:
                input_text = self._serialize_messages(invocation.messages)
            output_text = self._serialize_messages(invocation.output_messages)
            if not output_text:
                output_text = self._serialize_messages(
                    invocation.chat_generations
                )
            context = self._extract_context(invocation)
            retrieval_context = self._extract_retrieval_context(invocation)
            if not input_text or not output_text:
                return None
            return LLMTestCase(
                input=input_text,
                actual_output=output_text,
                context=context,
                retrieval_context=retrieval_context,
                additional_metadata=invocation.attributes or None,
                name=invocation.request_model,
            )
        if isinstance(invocation, AgentInvocation):
            input_chunks = []
            if invocation.system_instructions:
                input_chunks.append(invocation.system_instructions)
            if invocation.input_context:
                input_chunks.append(invocation.input_context)
            input_text = "\n\n".join(chunk for chunk in input_chunks if chunk)
            output_text = invocation.output_result or ""
            if not input_text or not output_text:
                return None
            context: list[str] | None = None
            if invocation.tools:
                context = ["Tools: " + ", ".join(invocation.tools)]
            return LLMTestCase(
                input=input_text,
                actual_output=output_text,
                context=context,
                retrieval_context=self._extract_retrieval_context(invocation),
                additional_metadata={
                    "agent_name": invocation.name,
                    "agent_type": invocation.agent_type,
                    **(invocation.attributes or {}),
                },
                name=invocation.operation,
            )
        return None

    def _run_deepeval(self, test_case: Any, metrics: Sequence[Any]) -> Any:
        from deepeval import evaluate as deepeval_evaluate
        from deepeval.evaluate.configs import AsyncConfig, DisplayConfig

        display_config = DisplayConfig(
            show_indicator=False, print_results=False
        )
        async_config = AsyncConfig(run_async=False)
        return deepeval_evaluate(
            [test_case],
            list(metrics),
            async_config=async_config,
            display_config=display_config,
        )

    def _convert_results(self, evaluation: Any) -> Sequence[EvaluationResult]:
        results: list[EvaluationResult] = []
        try:
            test_results = getattr(evaluation, "test_results", [])
        except Exception:  # pragma: no cover - defensive
            return self._error_results(
                "Unexpected Deepeval response", RuntimeError
            )
        for test in test_results:
            metrics_data = getattr(test, "metrics_data", []) or []
            for metric in metrics_data:
                name = getattr(metric, "name", "deepeval")
                score = getattr(metric, "score", None)
                reason = getattr(metric, "reason", None)
                success = getattr(metric, "success", None)
                threshold = getattr(metric, "threshold", None)
                evaluation_model = getattr(metric, "evaluation_model", None)
                evaluation_cost = getattr(metric, "evaluation_cost", None)
                verbose_logs = getattr(metric, "verbose_logs", None)
                strict_mode = getattr(metric, "strict_mode", None)
                error_msg = getattr(metric, "error", None)
                attributes: dict[str, Any] = {
                    "deepeval.success": success,
                }
                if threshold is not None:
                    attributes["deepeval.threshold"] = threshold
                if evaluation_model:
                    attributes["deepeval.evaluation_model"] = evaluation_model
                if evaluation_cost is not None:
                    attributes["deepeval.evaluation_cost"] = evaluation_cost
                if verbose_logs:
                    attributes["deepeval.verbose_logs"] = verbose_logs
                if strict_mode is not None:
                    attributes["deepeval.strict_mode"] = strict_mode
                if getattr(test, "name", None):
                    attributes.setdefault(
                        "deepeval.test_case", getattr(test, "name")
                    )
                if getattr(test, "success", None) is not None:
                    attributes.setdefault(
                        "deepeval.test_success", getattr(test, "success")
                    )
                error = None
                if error_msg:
                    error = Error(message=str(error_msg), type=RuntimeError)
                label = None
                if success is True:
                    label = "pass"
                elif success is False:
                    label = "fail"
                results.append(
                    EvaluationResult(
                        metric_name=name,
                        score=score
                        if isinstance(score, (int, float))
                        else None,
                        label=label,
                        explanation=reason,
                        error=error,
                        attributes=attributes,
                    )
                )
        return results

    def _error_results(
        self, message: str, error_type: type[BaseException]
    ) -> Sequence[EvaluationResult]:
        _LOGGER.warning("Deepeval evaluation failed: %s", message)
        return [
            EvaluationResult(
                metric_name=metric,
                explanation=message,
                error=Error(message=message, type=error_type),
                attributes={"deepeval.error": message},
            )
            for metric in self.metrics
        ]

    @staticmethod
    def _coerce_option(value: Any) -> Any:
        if isinstance(value, MappingABC):
            return {
                k: DeepevalEvaluator._coerce_option(v)
                for k, v in value.items()
            }
        if isinstance(value, (int, float, bool)):
            return value
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return text
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    @staticmethod
    def _serialize_messages(messages: Sequence[Any]) -> str:
        chunks: list[str] = []
        for message in messages or []:
            parts = getattr(message, "parts", [])
            for part in parts:
                if isinstance(part, Text):
                    chunks.append(part.content)
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    @staticmethod
    def _extract_context(invocation: LLMInvocation) -> list[str] | None:
        context_values: list[str] = []
        attr = invocation.attributes or {}
        for key in ("context", "additional_context"):
            context_values.extend(
                DeepevalEvaluator._flatten_to_strings(attr.get(key))
            )
        return [value for value in context_values if value] or None

    @staticmethod
    def _extract_retrieval_context(invocation: GenAI) -> list[str] | None:
        attr = invocation.attributes or {}
        retrieval_values: list[str] = []
        for key in (
            "retrieval_context",
            "retrieved_context",
            "retrieved_documents",
            "documents",
            "sources",
            "evidence",
        ):
            retrieval_values.extend(
                DeepevalEvaluator._flatten_to_strings(attr.get(key))
            )
        return [value for value in retrieval_values if value] or None

    @staticmethod
    def _flatten_to_strings(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, MappingABC):
            for key in ("content", "page_content", "text", "body", "value"):
                inner = value.get(key)
                if isinstance(inner, str):
                    return [inner]
                if inner is not None:
                    return DeepevalEvaluator._flatten_to_strings(inner)
            return [str(value)]
        if isinstance(value, SequenceABC) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            flattened: list[str] = []
            for item in value:
                flattened.extend(DeepevalEvaluator._flatten_to_strings(item))
            return flattened
        return [str(value)]

    def _missing_required_params(
        self, metric_cls: Any, test_case: Any
    ) -> list[str]:
        required = getattr(metric_cls, "_required_params", [])
        missing: list[str] = []
        for param in required:
            attr_name = getattr(param, "value", str(param))
            value = getattr(test_case, attr_name, None)
            if value is None:
                missing.append(attr_name)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(attr_name)
                continue
            if isinstance(value, SequenceABC) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                flattened = self._flatten_to_strings(value)
                if not flattened:
                    missing.append(attr_name)
        return missing

    @staticmethod
    def _default_model() -> str | None:
        import os

        model = (
            os.getenv("DEEPEVAL_EVALUATION_MODEL")
            or os.getenv("DEEPEVAL_MODEL")
            or os.getenv("OPENAI_MODEL")
        )
        if model:
            return model
        return "gpt-4o-mini"


def _factory(
    metrics: Iterable[str] | None = None,
    invocation_type: str | None = None,
    options: Mapping[str, Mapping[str, str]] | None = None,
) -> DeepevalEvaluator:
    return DeepevalEvaluator(
        metrics,
        invocation_type=invocation_type,
        options=options,
    )


_REGISTRATION = EvaluatorRegistration(
    factory=_factory,
    default_metrics_factory=lambda: _DEFAULT_METRICS,
)


def registration() -> EvaluatorRegistration:
    return _REGISTRATION


def register() -> None:
    register_evaluator(
        "deepeval",
        _REGISTRATION.factory,
        default_metrics=_REGISTRATION.default_metrics_factory,
    )


__all__ = [
    "DeepevalEvaluator",
    "registration",
    "register",
]
